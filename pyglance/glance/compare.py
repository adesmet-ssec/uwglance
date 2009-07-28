#!/usr/bin/env python
# encoding: utf-8
"""

Top-level routines to compare two files.


Created by rayg Apr 2009.
Copyright (c) 2009 University of Wisconsin SSEC. All rights reserved.
"""

import os, sys, logging, re, subprocess, datetime
import imp as imp
from pprint import pprint, pformat
from numpy import *
import pkg_resources

import glance.io as io
import glance.delta as delta
import glance.plot as plot
import glance.report as report

LOG = logging.getLogger(__name__)

glance_default_longitude_name = 'pixel_longitude' 
glance_default_latitude_name = 'pixel_latitude'

# these are the built in default settings
glance_analysis_defaults = {'epsilon': 0.0,
                            'missing_value': None,
                            'missing_value_alt_in_b': None, 
                            'epsilon_failure_tolerance': 0.0, 
                            'nonfinite_data_tolerance':  0.0 
                            }

def _cvt_names(namelist, epsilon, missing):
    """"if variable names are of the format name:epsilon, yield name,epsilon, missing
        otherwise yield name,default-epsilon,default-missing
    """
    for name in namelist:
        if ':' not in name:
            yield name, epsilon
        else:
            n,e,m = name.split(':')
            if not e: e = epsilon
            else: e = float(e)
            if not m: m = missing
            else: m = float(m)
            yield n, e, m

def _parse_varnames(names, terms, epsilon=0.0, missing=None):
    """filter variable names and substitute default epsilon and missing settings if none provided
    returns name,epsilon,missing triples
    >>> _parse_varnames( ['foo','bar', 'baz', 'zoom', 'cat'], ['f..:0.5:-999', 'ba.*:0.001', 'c.t::-9999'], 1e-7 )
    set([('foo', 0.5, -999.0), ('cat', 9.9999999999999995e-08, -9999.0), ('bar', 0.001, None), ('baz', 0.001, None)])
    """
    terms = [x.split(':') for x in terms]
    terms = [(re.compile(x[0]).match,x[1:]) for x in terms]
    def _cvt_em(eps=None, mis=None):
        eps = float(eps) if eps else epsilon
        mis = float(mis) if mis else missing
        return eps, mis
    sel = [ ((x,)+_cvt_em(*em)) for x in names for (t,em) in terms if t(x) ]
    return set(sel)

def _setup_file(fileNameAndPath, prefexText='') :
    '''
    open the provided file name/path and extract information on the md5sum and last modification time
    optional prefext text may be passed in for informational output formatting
    '''
    # some info to return
    fileInfo = {'path': fileNameAndPath}
    
    # open the file
    LOG.info(prefexText + "opening " + fileNameAndPath)
    fileObject = io.open(fileNameAndPath)
    
    # get the file md5sum
    tempSubProcess = subprocess.Popen("md5sum " + fileNameAndPath, shell=True, stdout=subprocess.PIPE)
    fileInfo['md5sum'] = tempSubProcess.communicate()[0].split()[0]
    LOG.info(prefexText + "file md5sum: " + str(fileInfo['md5sum']))
    
    # get the last modified stamp
    statsForFile = os.stat(fileNameAndPath)
    fileInfo['lastModifiedTime'] = datetime.datetime.fromtimestamp(statsForFile.st_mtime).ctime() # should time zone be forced?
    LOG.info (prefexText + "file was last modified: " + fileInfo['lastModifiedTime'])
    
    return fileObject, fileInfo

def _check_file_names(fileAObject, fileBObject) :
    """
    get information about the names in the two files and how they compare to each other
    """
    # get information about the variables stored in the files
    aNames = set(fileAObject())
    bNames = set(fileBObject())
    
    # get the variable names they have in common
    commonNames = aNames.intersection(bNames)
    # which names are unique to only one of the two files?
    uniqueToANames = aNames - commonNames
    uniqueToBNames = bNames - commonNames
    
    return {'sharedVars': commonNames,  'uniqueToAVars': uniqueToANames, 'uniqueToBVars': uniqueToBNames}

def _resolve_names(fileAObject, fileBObject, defaultValues,
                   requestedNames, usingConfigFileFormat=False) :
    """
    figure out which names the two files share and which are unique to each file, as well as which names
    were requested and are in both sets
    
    usingConfigFileFormat signals whether the requestedNames parameter will be in the form of the inputed
    names from the command line or a more complex dictionary holding information about the names read in
    from a configuration file
    
    Note: if we ever need a variable with different names in file A and B to be comparable, this logic
    will need to be changed.
    """
    # look at the names present in the two files and compare them
    nameComparison = _check_file_names(fileAObject, fileBObject)
    
    # figure out which set should be selected based on the user requested names
    fileCommonNames = nameComparison['sharedVars']
    finalNames = {}
    if (usingConfigFileFormat) :
        
        # if the user didn't ask for any, try everything
        if (requestedNames == {}) :
            finalFromCommandLine = _parse_varnames(fileCommonNames, ['.*'],
                                                   defaultValues['epsilon'], defaultValues['missing_value'])
            for name, epsilon, missing in finalFromCommandLine :
                # we'll use the variable's name as the display name for the time being
                finalNames[name] = {}
                # make sure we pick up any other controlling defaults
                finalNames[name].update(defaultValues) 
                # but override the values that would have been determined by _parse_varnames
                finalNames[name]['variable_name'] = name
                finalNames[name]['epsilon'] = epsilon
                
                # load the missing value if it was not provided
                missing_b = missing
                if missing is None:
                    missing   = fileAObject.missing_value(name)
                    missing_b = fileBObject.missing_value(name)
                finalNames[name]['missing_value'] = missing 
                finalNames[name]['missing_value_alt_in_b'] = missing_b
                
        # otherwise just do the ones the user asked for
        else : 
            # check each of the names the user asked for to see if it is either in the list of common names
            # or, if the user asked for an alternate name mapping in file B, if the two mapped names are in
            # files A and B respectively
            for name in requestedNames :
                if (name in fileCommonNames) | \
                        (requestedNames[name].has_key('alternate_name_in_B') and
                         (name in nameComparison['uniqueToAVars']) and
                         (requestedNames[name]['alternate_name_in_B'] in nameComparison['uniqueToBVars'])) :
                    finalNames[name] = defaultValues.copy()
                    finalNames[name]['variable_name'] = name
                    finalNames[name].update(requestedNames[name])
                    
                    # load the missing value if it was not provided
                    if finalNames[name]['missing_value'] is None :
                        finalNames[name]['missing_value'] = fileAObject.missing_value(name)
                    if not('missing_value_alt_in_b' in finalNames[name]) or (finalNames[name]['missing_value_alt_in_b'] is None) :
                        finalNames[name]['missing_value_alt_in_b'] = fileBObject.missing_value(name)
    else:
        # format command line input similarly to the stuff from the config file
        print (requestedNames)
        finalFromCommandLine = _parse_varnames(fileCommonNames, requestedNames,
                                               defaultValues['epsilon'], defaultValues['missing_value'])
        for name, epsilon, missing in finalFromCommandLine :
            ## we'll use the variable's name as the display name for the time being
            finalNames[name] = {}
            # make sure we pick up any other controlling defaults
            finalNames[name].update(defaultValues) 
            # but override the values that would have been determined by _parse_varnames
            finalNames[name]['variable_name'] = name
            finalNames[name]['epsilon'] = epsilon
            
            # load the missing value if it was not provided
            missing_b = missing
            if missing is None:
                missing   = fileAObject.missing_value(name)
                missing_b = fileBObject.missing_value(name)
            finalNames[name]['missing_value'] = missing 
            finalNames[name]['missing_value_alt_in_b'] = missing_b
    
    LOG.debug("Final selected set of variables to analyze:")
    LOG.debug(str(finalNames))
    
    return finalNames, nameComparison

def _load_config_or_options(optionsSet, originalArgs) :
    """
    load information on how the user wants to run the command either from the command line options or
    from a configuration file
    """
    
    # basic defaults for stuff we will need to return
    runInfo = {}
    runInfo['shouldIncludeReport'] = True
    runInfo['shouldIncludeImages'] = False
    runInfo['latitude'] = glance_default_latitude_name
    runInfo['longitude'] = glance_default_longitude_name
    runInfo['lon_lat_epsilon'] = 0.0
    runInfo['version'] = _get_glance_version_string()
    
    # by default, we don't have any particular variables to analyze
    desiredVariables = {}
    # use the built in default values, to start with
    defaultsToUse = glance_analysis_defaults.copy()
    
    requestedNames = None
    
    # set up the paths, they can only come from the command line
    paths = {}
    paths['a'], paths['b'] = originalArgs[:2] # todo, let caller control # of paths expected?
    paths['out'] = optionsSet.outputpath
    
    # check to see if the user wants to use a config file and if the path exists
    requestedConfigFile = optionsSet.configFile
    usedConfigFile = False
    if (not (requestedConfigFile is None)) and os.path.exists(requestedConfigFile):
        
        LOG.info ("Using Config File Settings")
        
        # this will handle relative paths, but not '~'?
        requestedConfigFile = os.path.abspath(os.path.expanduser(requestedConfigFile))
        
        # split out the file base name and the file path
        (filePath, fileName) = os.path.split(requestedConfigFile)
        splitFileName = fileName.split('.')
        fileBaseName = fileName[:-3] # remove the '.py' from the end
        
        # load the file
        print('loading config file: ' + str(requestedConfigFile))
        glanceRunConfig = imp.load_module(fileBaseName, file(requestedConfigFile, 'U'),
                                          filePath, ('.py' , 'U', 1))
        
        # get everything from the config file
        runInfo['shouldIncludeImages'] = glanceRunConfig.shouldIncludeImages
        runInfo.update(glanceRunConfig.lat_lon_info) # get info on the lat/lon variables
        
        # get any requested names
        requestedNames = glanceRunConfig.setOfVariables.copy()
        
        # user selected defaults, if they omit any we'll still be using the program defaults
        defaultsToUse.update(glanceRunConfig.defaultValues)
        
        # this is an exception, since it is not advertised to the user we don't expect it to be in the file
        # (at least not at the moment, it could be added later)
        runInfo['shouldIncludeReport'] = not optionsSet.imagesOnly 
        
        usedConfigFile = True
    
    # if we didn't get the info from the config file for some reason
    # (the user didn't want to, we couldn't, etc...) get it from the command line options
    if not usedConfigFile:
        
        LOG.info ('Using Command Line Settings')
        
        # so get everything from the options directly
        runInfo['shouldIncludeReport'] = not optionsSet.imagesOnly
        runInfo['shouldIncludeImages'] = not optionsSet.htmlOnly
        runInfo['latitude'] = optionsSet.latitudeVar or runInfo['latitude']
        runInfo['longitude'] = optionsSet.longitudeVar or runInfo['longitude']
        runInfo['lon_lat_epsilon'] = optionsSet.lonlatepsilon
        
        # get any requested names from the command line
        requestedNames = originalArgs[2:] or ['.*']
        
        # user selected defaults
        defaultsToUse['epsilon'] = optionsSet.epsilon
        defaultsToUse['missing_value'] = optionsSet.missing
        # there is no way to set the tolerances from the command line at the moment
    
    return paths, runInfo, defaultsToUse, requestedNames, usedConfigFile

def _get_and_analyze_lon_lat (fileObject, latitudeVariableName, longitudeVariableName) :
    """
    get the longitude and latitude data from the given file, assuming they are in the given variable names
    and analyze them to identify spacially invalid data (ie. data that would fall off the earth)
    """
    # get the data from the file
    longitudeData = array(fileObject[longitudeVariableName], dtype=float)
    latitudeData  = array(fileObject[latitudeVariableName],  dtype=float)
    
    # build a mask of our spacially invalid data
    invalidLatitude = (latitudeData < -90) | (latitudeData > 90)
    invalidLongitude = (longitudeData < -180)   | (longitudeData > 360)
    spaciallyInvalidMask = invalidLatitude | invalidLongitude
    
    # analyze our spacially invalid data
    percentageOfSpaciallyInvalidPts, numberOfSpaciallyInvalidPts = _get_percentage_from_mask(spaciallyInvalidMask)
    
    return longitudeData, latitudeData, spaciallyInvalidMask, {'totNumInvPts': numberOfSpaciallyInvalidPts,
                                                               'perInvPts': percentageOfSpaciallyInvalidPts}

def _get_percentage_from_mask(dataMask) :
    """
    given a mask that marks the elements we want the percentage of as True (and is the size of our original data),
    figure out what percentage of the whole they are
    """
    numMarkedDataPts = len(dataMask[dataMask].ravel())
    dataShape = dataMask.shape
    totalDataPts = dataShape[0] * dataShape[1]
    percentage = 100.0 * float(numMarkedDataPts) / float(totalDataPts)
    
    return percentage, numMarkedDataPts

def _check_lon_lat_equality(longitudeA, latitudeA,
                            longitudeB, latitudeB,
                            ignoreMaskA, ignoreMaskB,
                            llepsilon, doMakeImages, outputPath) :
    """
    check to make sure the longitude and latitude are equal everywhere that's not in the ignore masks
    if they are not and doMakeImages was passed as True, generate appropriate figures to show where
    return the number of points where they are not equal (0 would mean they're the same)
    """
    # first of all, if the latitude and longitude are not the same shape, then things can't ever be "equal"
    if (longitudeA.shape != longitudeB.shape) | (latitudeA.shape != latitudeB.shape) :
        return None
    
    lon_lat_not_equal_points_count = 0
    lon_lat_not_equal_points_percent = 0.0
    combinedIgnoreMask = ignoreMaskA | ignoreMaskB
    
    # get information about how the latitude and longitude differ
    longitudeDiff, finiteLongitudeMask, _, _, _, lon_not_equal_mask = delta.diff(longitudeA, longitudeB,
                                                                                     llepsilon,
                                                                                     ignoreMask=combinedIgnoreMask)
    latitudeDiff,  finiteLatitudeMask,  _, _, _, lat_not_equal_mask = delta.diff(latitudeA,  latitudeB,
                                                                                 llepsilon,
                                                                                 ignoreMask=combinedIgnoreMask)
    lon_lat_not_equal_mask = lon_not_equal_mask | lat_not_equal_mask
    lon_lat_not_equal_points_count = sum(lon_lat_not_equal_mask.ravel())
    lon_lat_not_equal_points_percent = (float(lon_lat_not_equal_points_count) / float(lon_lat_not_equal_mask.size)) * 100.0
    
    # if we have unequal points, create user legible info about the problem
    if (lon_lat_not_equal_points_count > 0) :
        LOG.warn("Possible mismatch in values stored in file a and file b longitude and latitude values."
                 + " Depending on the degree of mismatch, some data value comparisons may be "
                 + "distorted or spacially nonsensical.")
        # if we are making images, make two showing the invalid lons/lats
        if (doMakeImages) :
            plot.plot_and_save_spacial_trouble(longitudeA, latitudeA,
                                               lon_lat_not_equal_mask,
                                               ignoreMaskA,
                                               "A", "Lon./Lat. Points Mismatched between A and B\n" +
                                               "(Shown in A)",
                                               "LonLatMismatch",
                                               outputPath, True)
            plot.plot_and_save_spacial_trouble(longitudeB, latitudeB,
                                               lon_lat_not_equal_mask,
                                               ignoreMaskB,
                                               "B", "Lon./Lat. Points Mismatched between A and B\n" +
                                               "(Shown in B)",
                                               "LonLatMismatch",
                                               outputPath, True)
    
    # setup our return data
    returnInfo = {}
    returnInfo['lon_lat_not_equal_points_count'] = lon_lat_not_equal_points_count
    returnInfo['lon_lat_not_equal_points_percent'] = lon_lat_not_equal_points_percent
    
    return returnInfo

def _compare_spatial_invalidity(invalid_in_a_mask, invalid_in_b_mask, spatial_info,
                                longitude_a, longitude_b, latitude_a, latitude_b,
                                do_include_images, output_path) :
    """
    Given information about where the two files are spatially invalid, figure
    out what invalidity they share and save information or plots for later use
    also build a shared longitude/latitude based on A but also including valid
    points in B
    """
    
    # for convenience,
    # make a combined mask
    invalid_in_common_mask = invalid_in_a_mask | invalid_in_b_mask
    # make a "common" latitude based on A
    longitude_common = longitude_a
    latitude_common = latitude_a
    
    # compare our spacialy invalid info
    spatial_info['perInvPtsInBoth'] = spatial_info['file A']['perInvPts']
            # a default that will hold if the two files have the same spatially invalid pts
    if not all(invalid_in_a_mask.ravel() == invalid_in_b_mask.ravel()) : 
        LOG.info("Mismatch in number of spatially invalid points. " +
                 "Files may not have corresponding data where expected.")
        
        # figure out which points are only valid in one of the two files
        valid_only_in_mask_a = (~invalid_in_a_mask) & invalid_in_b_mask
        spatial_info['file A']['numInvPts'] = sum(valid_only_in_mask_a.ravel())
        valid_only_in_mask_b = (~invalid_in_b_mask) & invalid_in_a_mask
        spatial_info['file B']['numInvPts'] = sum(valid_only_in_mask_b.ravel())
        
        # so how many do they have together?
        spatial_info['perInvPtsInBoth'] = _get_percentage_from_mask(invalid_in_common_mask)[0]
        # make a "clean" version of the lon/lat
        longitude_common[valid_only_in_mask_a] = longitude_a[valid_only_in_mask_a]
        longitude_common[valid_only_in_mask_b] = longitude_b[valid_only_in_mask_b]
        latitude_common [valid_only_in_mask_a] = latitude_a [valid_only_in_mask_a]
        latitude_common [valid_only_in_mask_b] = latitude_b [valid_only_in_mask_b]
        
        # plot the points that are only valid one file and not the other
        if (spatial_info['file A']['numInvPts'] > 0) and (do_include_images) :
            plot.plot_and_save_spacial_trouble(longitude_a, latitude_a,
                                               valid_only_in_mask_a,
                                               invalid_in_a_mask,
                                               "A", "Points only valid in\nFile A\'s longitude & latitude",
                                               "SpatialMismatch",
                                               output_path, True)
        if (spatial_info['file B']['numInvPts'] > 0) and (do_include_images) :
            plot.plot_and_save_spacial_trouble(longitude_b, latitude_b,
                                               valid_only_in_mask_b,
                                               invalid_in_b_mask,
                                               "B", "Points only valid in\nFile B\'s longitude & latitude",
                                               "SpatialMismatch",
                                               output_path, True)
    
    return invalid_in_common_mask, spatial_info, longitude_common, latitude_common

def _open_and_process_files (args, numFilesExpected):
    """
    open files listed in the args and get information about the variables in them
    """
    # get all the file names
    fileNames = args[:numFilesExpected]
    # open all the files & get their variable names
    files = {}
    commonNames = None
    for fileName in fileNames:
        LOG.info("opening %s" % fileName)
        files[fileName] = {}
        tempFileObject = (io.open(fileName))
        files[fileName]['fileObject'] = tempFileObject
        tempNames = set(tempFileObject())
        files[fileName]['varNames'] = tempNames
        if commonNames is None :
            commonNames = tempNames
        else :
            commonNames = commonNames.intersection(tempNames)
    files['commonVarNames'] = commonNames
    
    return files

def _check_pass_or_fail(varRunInfo, variableStats, defaultValues) :
    """
    Check whether the variable passed analysis, failed analysis, or
    did not need to be quantitatively tested
    """
    didPass = None
    
    # get our tolerance values
    
    # get the tolerance for failures in comparison compared to epsilon
    epsilonTolerance = None
    if ('epsilon_failure_tolerance' in varRunInfo) :
        epsilonTolerance = varRunInfo['epsilon_failure_tolerance']
    else :
        epsilonTolerance = defaultValues['epsilon_failure_tolerance']
    # get the tolerance for failures in amount of nonfinite data
    # found in spatially valid areas
    nonfiniteTolerance = None
    if ('nonfinite_data_tolerance'  in varRunInfo) :
        nonfiniteTolerance = varRunInfo['nonfinite_data_tolerance']
    else :
        nonfiniteTolerance = defaultValues['nonfinite_data_tolerance']
    
    # test to see if we passed or failed
    
    # check for our epsilon tolerance
    if not (epsilonTolerance is None) :
        failed_fraction = variableStats['Numerical Comparison Statistics']['diff_outside_epsilon_fraction']
        didPass = failed_fraction <= epsilonTolerance
    # check to see if it failed on nonfinite data
    if not (nonfiniteTolerance is None) :
        non_finite_pts = variableStats['Finite Data Statistics']['finite_in_only_one_count']
        non_finite_pts = non_finite_pts + variableStats['Missing Value Statistics']['common_missing_count']
        non_finite_pts = non_finite_pts + variableStats['NaN Statistics']['common_nan_count']
        non_finite_fraction = float(non_finite_pts) / float(variableStats['General Statistics']['num_data_points'])
        passedNonFinite = non_finite_fraction <= nonfiniteTolerance 
        if (didPass is None) :
            didPass = passedNonFinite
        else :
            didPass = didPass and passedNonFinite
    
    return didPass

def _get_glance_version_string() :
    version_num = pkg_resources.require('glance')[0].version
    
    return "glance, version " + str(version_num) 

def main():
    import optparse
    usage = """
%prog [options] 
run "%prog help" to list commands
examples:

python -m glance.compare info A.hdf
python -m glance.compare stats A.hdf B.hdf '.*_prof_retr_.*:1e-4' 'nwp_._index:0'
python -m glance.compare plotDiffs A.hdf B.hdf
python -m glance compare reportGen A.hdf B.hdf
python -m glance 

"""
    parser = optparse.OptionParser(usage)
    parser.add_option('-t', '--test', dest="self_test",
                    action="store_true", default=False, help="run internal unit tests")            
    parser.add_option('-q', '--quiet', dest="quiet",
                    action="store_true", default=False, help="only error output")
    parser.add_option('-v', '--verbose', dest="verbose",
                    action="store_true", default=False, help="enable more informational output")   
    parser.add_option('-w', '--debug', dest="debug",
                    action="store_true", default=False, help="enable debug output")   
    parser.add_option('-e', '--epsilon', dest="epsilon", type='float', default=0.0,
                    help="set default epsilon value for comparison threshold")   
    parser.add_option('-m', '--missing', dest="missing", type='float', default=None,
                    help="set default missing-value")
    #report generation related options
    parser.add_option('-p', '--outputpath', dest="outputpath", type='string', default='./',
                    help="set path to output directory")
    parser.add_option('-o', '--longitude', dest="longitudeVar", type='string',
                    help="set name of longitude variable")
    parser.add_option('-a', '--latitude', dest="latitudeVar", type='string',
                    help="set name of latitude variable")
    parser.add_option('-i', '--imagesonly', dest="imagesOnly", 
                      action="store_true", default=False,
                      help="generate only image files (no html report)")
    parser.add_option('-r', '--reportonly', dest="htmlOnly", 
                      action="store_true", default=False,
                      help="generate only html report files (no images)")
    parser.add_option('-c', '--configfile', dest="configFile", type='string', default=None,
                      help="set optional configuration file")
    parser.add_option('-l', '--llepsilon', dest='lonlatepsilon', type='float', default=0.0,
                      help="set default epsilon for longitude and latitude comparsion")
    parser.add_option('-n', '--version', dest='version',
                      action="store_true", default=False, help="view the glance version")
    
                    
    options, args = parser.parse_args()
    if options.self_test:
        import doctest
        doctest.testmod()
        sys.exit(2)

    lvl = logging.WARNING
    if options.debug: lvl = logging.DEBUG
    elif options.verbose: lvl = logging.INFO
    elif options.quiet: lvl = logging.ERROR
    logging.basicConfig(level = lvl)
    
    # display the version
    if options.version :
        print (_get_glance_version_string() + '\n')

    commands = {}
    prior = None
    prior = dict(locals())
    
    def info(*args):
        """list information about a list of files
        List available variables for comparison.
        """
        for fn in args:
            lal = list(io.open(fn)())
            lal.sort()
            print fn + ': ' + ('\n  ' + ' '*len(fn)).join(lal)
    
    def sdr_cris(*args):
        """compare sdr_cris output
        parameters are variable name followed by detector number
        sdr_cris desired.h5 actual.h5 ESRealLW 0
        """ # TODO ******* standardize with method?
        afn,bfn = args[:2]
        LOG.info("opening %s" % afn)
        a = io.open(afn)
        LOG.info("opening %s" % bfn)
        b = io.open(bfn)
        # shape is [scanline, field, detector, wnum]
        vname = '/All_Data/CrIS-SDR_All/' + args[2]
        det_idx = int(args[3])
        def get(f):
            spc = f[vname][:,:,det_idx,:]
            nsl,nfor,nwn = spc.shape
            return spc.reshape( (nsl*nfor,nwn) )
        aspc = get(a)
        bspc = get(b)
        plot.compare_spectra(bspc,aspc)
        plot.show()
    
    def noisecheck(*args):
        """gives statistics for dataset comparisons against truth with and without noise
        usage: noisecheck truth-file noise-file actual-file variable1{:epsilon{:missing}} {variable2...}
        glance noisecheck /Volumes/snaapy/data/justins/abi_graffir/coreg/pure/l2_data/geocatL2.GOES-R.2005155.220000.hdf.gz /Volumes/snaapy/data/justins/abi_graffir/noise/noise1x/l2_data/geocatL2.GOES-R.2005155.220000.hdf 
        """ # TODO ******* standardize with method?
        afn,noizfn,bfn = args[:3]
        LOG.info("opening truth file %s" % afn)
        a = io.open(afn)
        LOG.info("opening actual file %s" % noizfn)
        noiz = io.open(noizfn)
        LOG.info("opening noise file %s" % bfn)
        b = io.open(bfn)
        
        anames = set(a())
        bnames = set(b()) 
        cnames = anames.intersection(bnames) # common names
        pats = args[3:] or ['.*']
        names = _parse_varnames( cnames, pats, options.epsilon, options.missing )
        for name,epsilon,missing in names:
            aData = a[name]
            bData = b[name]
            nData = noiz[name]
            if missing is None:
                amiss = a.missing_value(name)
                bmiss = b.missing_value(name)
            else:
                amiss,bmiss = missing,missing
            x = aData
            y = bData
            z = nData
            def scat(x,xn,y):
                from pylab import plot,show,scatter
                scatter(x,y)
                show()
            nfo = delta.rms_corr_withnoise(x,y,z,epsilon,(amiss,bmiss),plot=scat)
            print '-'*32
            print name
            for kv in sorted(nfo.items()):
                print '  %s: %s' % kv
    
    def stats(*args):
        """create statistics summary of variables
        Summarize difference statistics between listed variables.
        If no variable names are given, summarize all common variables.
        Variable names can be of the form varname:epsilon:missing to use non-default epsilon or missing value.
        Variable names can be regular expressions, e.g. 'image.*' or '.*prof_retr.*::-999'
        Either epsilon or missing can be empty to stay with default.
        If _FillValue is an attribute of a variable, that will be used to find missing values where no value is given.
        Run with -v to get more detailed information on statistics.
        Examples:
         python -m glance.compare stats hdffile1 hdffile2
         python -m glance.compare stats --epsilon=0.00001 A.hdf B.hdf baseline_cmask_seviri_cloud_mask:0.002:
         python -m glance.compare -w stats --epsilon=0.00001 A.hdf A.hdf imager_prof_retr_abi_total_precipitable_water_low::-999
        """ 
        afn,bfn = args[:2]
        filesInfo = _open_and_process_files(args, 2)
        aFile = filesInfo[afn]['fileObject']
        bFile = filesInfo[bfn]['fileObject']
        
        pats = args[2:] or ['.*']
        names = _parse_varnames( filesInfo['commonVarNames'], pats, options.epsilon, options.missing )
        LOG.debug(str(names))
        doc_each = (options.verbose or options.debug) and len(names)==1
        doc_atend = (options.verbose or options.debug) and len(names)!=1
        for name,epsilon,missing in names:
            aData = aFile[name]
            bData = bFile[name]
            if missing is None:
                amiss = aFile.missing_value(name)
                bmiss = bFile.missing_value(name)
            else:
                amiss,bmiss = missing,missing
            LOG.debug('comparing %s with epsilon %s and missing %s,%s' % (name,epsilon,amiss,bmiss))
            aval = aData
            bval = bData
            print '-'*32
            print name
            print 
            lal = list(delta.summarize(aval,bval,epsilon,(amiss,bmiss)).items()) 
            # lal = list(delta.stats(*delta.diff(aval,bval,epsilon,(amiss,bmiss))).items())
            lal.sort()
            for dictionary_title, dict_data in lal:
                print '%s' %  dictionary_title
                dict_data
                for each_stat in sorted(list(dict_data)):
                    print '  %s: %s' % (each_stat, dict_data[each_stat])
                    if doc_each: print('    ' + delta.STATISTICS_DOC[each_stat])
                print 
        if doc_atend:
            print('\n\n' + delta.STATISTICS_DOC_STR)

    def plotDiffs(*args) :
        """generate a set of images comparing two files
        This option creates a set of graphical comparisons of variables in the two given hdf files.
        The images detailing the differences between variables in the two hdf files will be
        generated and saved to disk. 
        Variables to be compared may be specified after the names of the two input files. If no variables
        are specified, all variables that match the shape of the longitude and latitude will be compared.
        Specified variables that do not exist, do not match the correct data shape, or are the longitude/latitude
        variables will be ignored.
        The user may also use the notation variable_name:epsilon:missing_value to specify the acceptible epsilon
        for comparison and the missing_value which indicates missing data. If one or both of these values is absent
        (in the case of variable_name:epsilon: variable_name::missing_value or just variable_name) the default value
        of 0.0 will be used for epsilon and no missing values will be analyzed. 
        The created images will be stored in the provided path, or if no path is provided, they will be stored in
        the current directory.
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used.
        Examples:
         python -m glance.compare plotDiffs A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         python -m glance.compare --outputpath=/path/where/output/will/be/placed/ plotDiffs A.hdf B.hdf
         python -m glance.compare plotDiffs --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
        """
        # set the options so that a report will not be generated
        options.imagesOnly = True
        
        # make the images
        reportGen(*args)
        
        return

    def reportGen(*args) :
        """generate a report comparing two files
        This option creates a report comparing variables in the two given hdf files.
        An html report and images detailing the differences between variables in the two hdf files will be
        generated and saved to disk. The images will be embedded in the report or visible as separate .png files.
        Variables to be compared may be specified after the names of the two input files. If no variables
        are specified, all variables that match the shape of the longitude and latitude will be compared.
        Specified variables that do not exist, do not match the correct data shape, or are the longitude/latitude
        variables will be ignored.
        The user may also use the notation variable_name:epsilon:missing_value to specify the acceptible epsilon
        for comparison and the missing_value which indicates missing data. If one or both of these values is absent
        (in the case of variable_name:epsilon: variable_name::missing_value or just variable_name) the default value
        of 0.0 will be used for epsilon and no missing values will be analyzed. 
        The html report page(s) and any created images will be stored in the provided path, or if no path is provided,
        they will be stored in the current directory.
        If for some reason you would prefer to generate the report without images, use the --reportonly option. This
        option will generate the html report but omit the images. This may be significantly faster, depending on
        your system, but the differences between the files may be quite a bit more difficult to interpret.
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used.
        Examples:
         python -m glance.compare reportGen A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         python -m glance.compare --outputpath=/path/where/output/will/be/placed/ reportGen A.hdf B.hdf
         python -m glance.compare reportGen --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
         python -m glance.compare reportGen --imagesonly A.hdf B.hdf
        """
        
        # load the user settings from either the command line or a user defined config file
        pathsTemp, runInfo, defaultValues, requestedNames, usedConfigFile = _load_config_or_options(options, args)
        
        # note some of this information for debugging purposes
        LOG.debug('paths: ' +           str(pathsTemp))
        LOG.debug('defaults: ' +        str(defaultValues))
        LOG.debug('run information: ' + str(runInfo))
        
        # if we wouldn't generate anything, just stop now
        if (not runInfo['shouldIncludeImages']) and (not runInfo['shouldIncludeReport']) :
            LOG.warn("User selection of no image generation and no report generation will result in no " +
                     "content being generated. Aborting report generation function.")
            return
        
        # get info on who's doing the run and where
        runInfo['machine'] = os.uname()[1] # the name of the machine running the report
        runInfo['user'] = os.getlogin() # the name of the user running the report
        
        # deal with the input and output files
        outputPath = pathsTemp['out']
        if not (os.path.isdir(outputPath)) :
            LOG.info("Specified output directory (" + outputPath + ") does not exist.")
            LOG.info("Creating output directory.")
            os.makedirs(outputPath)
        # open the files
        files = {}
        LOG.info("Processing File A:")
        aFile, files['file A'] = _setup_file(pathsTemp['a'], "\t")
        LOG.info("Processing File B:")
        bFile, files['file B'] = _setup_file(pathsTemp['b'], "\t")
        
        # get information about the names the user requested
        finalNames, nameStats = _resolve_names(aFile, bFile,
                                               defaultValues,
                                               requestedNames, usedConfigFile)
        
        # get and analyze our longitude and latitude data
        spatialInfo = {}
        b_longitude = runInfo['longitude']
        b_latitude  = runInfo['latitude']
        if ('longitude_alt_name_in_b' in runInfo) :
            b_longitude = runInfo['longitude_alt_name_in_b']
        if ( 'latitude_alt_name_in_b' in runInfo):
            b_latitude  = runInfo['latitude_alt_name_in_b']
        longitudeA, latitudeA, spaciallyInvalidMaskA, spatialInfo['file A'] = \
            _get_and_analyze_lon_lat (aFile, runInfo['latitude'], runInfo['longitude'])
        longitudeB, latitudeB, spaciallyInvalidMaskB, spatialInfo['file B'] = \
            _get_and_analyze_lon_lat (bFile, b_latitude, b_longitude)
        
        # test the "valid" values in our lon/lat
        moreSpatialInfo = _check_lon_lat_equality(longitudeA, latitudeA, longitudeB, latitudeB,
                                                  spaciallyInvalidMaskA, spaciallyInvalidMaskB,
                                                  runInfo['lon_lat_epsilon'], runInfo['shouldIncludeImages'],
                                                  outputPath)
        # if we got the worst type of error result from the comparison we need to stop now, because the data is too
        # dissimilar to be used
        if moreSpatialInfo is None :
            LOG.warn("Unable to reconcile sizes of longitude and latitude for variables "
                     + str(runInfo['longitude']) + str(longitudeA.shape) + "/"
                     + str(runInfo['latitude'])  + str(latitudeA.shape) + " in file A and variables "
                     + str(b_longitude) + str(longitudeB.shape) + "/"
                     + str(b_latitude)  + str(latitudeB.shape) + " in file B. Aborting attempt to compare files.")
            sys.exit(1) # things have gone wrong
        # update our existing spatial information
        spatialInfo.update(moreSpatialInfo)
        # if we have some points outside epsilon, we still want to make a report to show the user this problem, but
        # we can't trust most of our other comparison images
        if spatialInfo['lon_lat_not_equal_points_count'] > 0 :
            runInfo['short_circuit_diffs'] = True # I could simply run the above test every time, but this is simpler and clearer
        
        # compare our spatially invalid info to see if the two files have invalid longitudes and latitudes in the same places
        spaciallyInvalidMask, spatialInfo, longitudeCommon, latitudeCommon = \
                                _compare_spatial_invalidity(spaciallyInvalidMaskA, spaciallyInvalidMaskB, spatialInfo,
                                                            longitudeA, longitudeB, latitudeA, latitudeB,
                                                            runInfo['shouldIncludeImages'], outputPath)
            
        # set some things up to hold info for our reports
        
        # this will hold our variable report information in the form
        # [var_name] = {"var_stats": dictionary of statistics info, "run_info": information specific to that variable run,
        #               "data": {"A": data from file A, "B": data from file B}}
        variableAnalysisInfo = {}
        
        # go through each of the possible variables in our files
        # and make a report section with images for whichever ones we can
        for name in finalNames:
            
            # pull out the information for this variable analysis run
            varRunInfo = finalNames[name].copy()
            
            # make some local copies of our name info for display and labeling
            displayName = name
            if (varRunInfo.has_key('display_name')) :
                displayName = varRunInfo['display_name']
            explanationName = name
            if (varRunInfo.has_key('alternate_name_in_B')) :
                explanationName = explanationName + " / " + varRunInfo['alternate_name_in_B']
            explanationName = displayName + '(' + explanationName + ')'
            print('analyzing: ' + explanationName + ')')
            
            # if B has an alternate variable name, figure that out
            has_alt_B_variable = False
            b_variable = varRunInfo['variable_name']
            if (varRunInfo.has_key('alternate_name_in_B')) :
                has_alt_B_variable = True
                b_variable = varRunInfo['alternate_name_in_B']
            
            # get the data for the variable 
            aData = aFile[varRunInfo['variable_name']]
            bData = bFile[b_variable]
            
            # check if this data can be displayed
            if ((aData.shape == bData.shape) and
                (aData.shape == longitudeCommon.shape) and
                (bData.shape == longitudeCommon.shape)) :
                
                # build a dictionary of information on the variable
                variableAnalysisInfo[varRunInfo['variable_name']] = {}
                variableAnalysisInfo[varRunInfo['variable_name']]['data'] = {'A': aData,
                                                                             'B': bData}
                variableAnalysisInfo[varRunInfo['variable_name']]['var_stats'] = delta.summarize(aData, bData,
                                                                                                 varRunInfo['epsilon'],
                                                                                                 (varRunInfo['missing_value'],
                                                                                                  varRunInfo['missing_value_alt_in_b']),
                                                                                                 spaciallyInvalidMaskA, spaciallyInvalidMaskB)
                # add a little additional info to our variable run info before we squirrel it away
                varRunInfo['time'] = datetime.datetime.ctime(datetime.datetime.now()) 
                passedFraction = (1.0 - variableAnalysisInfo[name]['var_stats']
                                  ['Numerical Comparison Statistics']['diff_outside_epsilon_fraction'])
                varRunInfo['did_pass'] = _check_pass_or_fail(varRunInfo,
                                                             variableAnalysisInfo[name]['var_stats'],
                                                             defaultValues)
                variableAnalysisInfo[varRunInfo['variable_name']]['run_info'] = varRunInfo
                variableAnalysisInfo[varRunInfo['variable_name']]['exp_name'] = explanationName
                
            # if we can't compare the variable, we should tell the user 
            else :
                LOG.warn(explanationName + ' ' + 
                         'could not be compared. This may be because the data for this variable does not match in shape ' +
                         'between the two files or the data may not match the shape of the selected longitude and ' +
                         'latitude variables.')
        
        # from this point on, we will be forking to create child processes so we can parallelize our image and
        # report generation
        
        isParent = True 
        childPids = []
        
        # loop to create the images for all our variables
        if (runInfo['shouldIncludeImages']) :
            for name in variableAnalysisInfo :
                # create a child to handle this variable's images
                pid = os.fork()
                isParent = not (pid is 0)
                if (isParent) :
                    childPids.append(pid)
                    LOG.debug ("Started child process (pid: " + str(pid) + ") to create reports for variable " + name)
                else :
                    # create the images comparing that variable
                    print("\tcreating figures for: " + variableAnalysisInfo[name]['exp_name'])
                    plot.plot_and_save_figure_comparison(variableAnalysisInfo[name]['data']['A'],
                                                         variableAnalysisInfo[name]['data']['B'],
                                                         variableAnalysisInfo[name]['run_info'],
                                                         files['file A']['path'],
                                                         files['file B']['path'],
                                                         latitudeA, longitudeA,
                                                         latitudeB, longitudeB,
                                                         latitudeCommon, longitudeCommon,
                                                         spaciallyInvalidMaskA,
                                                         spaciallyInvalidMaskB,
                                                         spaciallyInvalidMask,
                                                         outputPath, True)
                    print("\tfinished creating figures for: " + variableAnalysisInfo[name]['exp_name'])
                    sys.exit(0) # this child has successfully finished it's tasks
        
        # reports are fast, so the parent thread will just do this
        # generate our general report pages once we've looked at all the variables
        if (runInfo['shouldIncludeReport']) :
            
            # this is going to be in the form
            # [var_name] = {"passEpsilonPercent": percent ok with epsilon, "epsilon": epsilon)
            variableComparisons = {}
            
            # generate the variable reports
            for name in variableAnalysisInfo :
                
                # hang on to our good % and other info to describe our comparison
                passedPercent = (1.0 - variableAnalysisInfo[name]['var_stats']
                                  ['Numerical Comparison Statistics']['diff_outside_epsilon_fraction']) * 100.0
                variableComparisons[name] = {'pass_epsilon_percent': passedPercent,
                                             'variable_run_info': variableAnalysisInfo[name]['run_info']
                                             }
                
                print ('\tgenerating report for: ' + variableAnalysisInfo[name]['exp_name']) 
                report.generate_and_save_variable_report(files,
                                                         variableAnalysisInfo[name]['run_info'], runInfo,
                                                         variableAnalysisInfo[name]['var_stats'],
                                                         spatialInfo,
                                                         outputPath, name + ".html")
            
            print ('generating summary report')
            # get the current time
            runInfo['time'] = datetime.datetime.ctime(datetime.datetime.now())
            # generate the report summary page
            report.generate_and_save_summary_report(files,
                                                    outputPath, 'index.html',
                                                    runInfo,
                                                    variableComparisons, 
                                                    spatialInfo,
                                                    nameStats)
            # make the glossary
            print ('generating glossary')
            report.generate_and_save_doc_page(delta.STATISTICS_DOC, outputPath)
        
        # if we're the parent, wait for any children to catch up
        if isParent:
            if len(childPids) > 0 :
                print ("waiting for completion of report and/or figure generation...")
            for pid in childPids:
                os.waitpid(pid, 0)
        
        print("... report and figure generation complete")
        return
    
    """
    # This was used to modify files for testing and should not be uncommented
    # unless you intend to use it only temporarily for testing purposes
    # at the moment it is not written very generally (only works with hdf4),
    # requires you to use 'from pyhdf.SD import SD, SDS' and change io to load
    # files in write mode rather than read only
    def make_renamed_variable_copy(*args) :
        '''
        make a copy of a variable in a file using the new name given by the user
        '''
        file_path = args[0]
        old_var_name = args[1]
        new_var_name = args[2]
        
        print ("Copying variable \'" + old_var_name + "\' to \'" + new_var_name
               + "\' in file " + file_path)
        
        # open the file and get the old variable
        LOG.info("\topening " + file_path)
        file_object = io.open(file_path)
        LOG.info("\tgetting " + old_var_name)
        variable_object_old = file_object.get_variable_object(old_var_name)
        temp, old_rank, old_shape, old_type, old_num_attributes = SDS.info(variable_object_old)
        old_attributes = SDS.attributes(variable_object_old)
        
        # make a copy of the variable with the new name
        LOG.info("\tsaving " + new_var_name)
        variable_object_new = SD.create(file_object, new_var_name, old_type, old_shape)
        SDS.set(variable_object_new, variable_object_old[:])
        '''  TODO, attribute copying is not working yet
        for attribute_name in old_attributes :
            variable_object_new[attribute_name] = variable_object_old[attribute_name]
        '''
        
        # close up all our access objects
        SDS.endaccess(variable_object_old)
        SDS.endaccess(variable_object_new)
        SD.end(file_object)
        
        return
    """

    # def build(*args):
    #     """build summary
    #     build extended info
    #     """
    #     LOG.info("building database tables")
    #     
    # def grant(*args):
    #     """grant summary
    #     grant extended info
    #     """
    #     LOG.info("granting permissions for tables")
    #     
    # def index(*args):
    #     """index summary
    #     index extended info
    #     """
    #     LOG.info("creating indices for tables")
        
    def help(command=None):
        """print help for a specific command or list of commands
        e.g. help stats
        """
        if command is None: 
            # print first line of docstring
            for cmd in commands:
                ds = commands[cmd].__doc__.split('\n')[0]
                print "%-16s %s" % (cmd,ds)
        else:
            print commands[command].__doc__
            
    # def test():
    #     "run tests"
    #     test1()
    #     
    commands.update(dict(x for x in locals().items() if x[0] not in prior))    
    
    if (not args) or (args[0] not in commands): 
        parser.print_help()
        help()
        return 9
    else:
        locals()[args[0]](*args[1:])

    return 0


if __name__=='__main__':
    sys.exit(main())