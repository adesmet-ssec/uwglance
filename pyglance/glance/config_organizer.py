#!/usr/bin/env python
# encoding: utf-8
"""

This module handles organizing the various configuration information that comes into glance.
This may include information from .py config files, options from the command line, or other
sources passed in by people calling glance library calls programatically.

Created by evas Dec 2012.
Copyright (c) 2012 University of Wisconsin SSEC. All rights reserved.
"""

import os, sys, imp, logging, re

import glance.io as io
from glance.constants import *

from glance.util import clean_path

LOG = logging.getLogger(__name__)

# these are the built in defaults for the settings
glance_setting_defaults = {
                           DO_MAKE_REPORT_KEY:         True,
                           DO_MAKE_IMAGES_KEY:         False,
                           DO_MAKE_FORKS_KEY:          False,
                           DO_CLEAR_MEM_THREADED_KEY:  False,
                           USE_SHARED_ORIG_RANGE_KEY:  False,
                           USE_NO_LON_OR_LAT_VARS_KEY: False,
                           DETAIL_DPI_KEY:             150,
                           THUMBNAIL_DPI_KEY:          50
                          }

# these are the built in longitude/latitude defaults
glance_lon_lat_defaults = {
                           LONGITUDE_NAME_KEY:        'pixel_longitude',
                           LATITUDE_NAME_KEY:         'pixel_latitude',
                           LON_LAT_EPSILON_KEY:       0.0,
                           LON_FILTER_FUNCTION_A_KEY: None,
                           LAT_FILTER_FUNCTION_A_KEY: None,
                           LON_FILTER_FUNCTION_B_KEY: None,
                           LAT_FILTER_FUNCTION_B_KEY: None
                          }

# these are the built in default settings for the variable analysis
glance_analysis_defaults = {
                            EPSILON_KEY:                0.0,
                            EPSILON_PERCENT_KEY:        None,
                            FILL_VALUE_KEY:             None,
                            EPSILON_FAIL_TOLERANCE_KEY: 0.0,
                            NONFINITE_TOLERANCE_KEY:    0.0,
                            TOTAL_FAIL_TOLERANCE_KEY:   None,
                            MIN_OK_R_SQUARED_COEFF_KEY: None,
                            DO_IMAGES_ONLY_ON_FAIL_KEY: False
                           }

def parse_varnames(names, terms, epsilon=0.0, missing=None):
    """filter variable names and substitute default epsilon and missing settings if none provided
    returns (variable name, epsilon, missing) triples
    
    >>> _parse_varnames( ['foo','bar', 'baz', 'zoom', 'cat'], ['f..:0.5:-999', 'ba.*:0.001', 'c.t::-9999'], 1e-7 )
    set([('foo', 0.5, -999.0), ('cat', 9.9999999999999995e-08, -9999.0), ('bar', 0.001, None), ('baz', 0.001, None)])
    
    names   - all the variable names in the file (ie. names that should be considered valid)
    terms   - variable selection terms given from the command line
    epsilon - a default epsilon to be used for all variables that do not have a specific epsilon given
    missing - a default fill value to be used for all variables that do not have a specific fill value given
    """
    terms = [x.split(':') for x in terms]
    terms = [(re.compile(x[0]).match,x[1:]) for x in terms]
    def _cvt_em(eps=None, mis=None):
        eps = float(eps) if eps else epsilon
        mis = float(mis) if mis else missing
        return eps, mis
    sel = [ ((x,)+_cvt_em(*em)) for x in names for (t,em) in terms if t(x) ]
    return set(sel)

def _check_shared_names (nameSetA, nameSetB) :
    """
    compare the names in the two sets
    """
    
    # what names do they have in common?
    commonNames = nameSetA.intersection(nameSetB)
    # what names are unique to each set?
    uniqueToANames = nameSetA - commonNames
    uniqueToBNames = nameSetB - commonNames
    
    return {SHARED_VARIABLE_NAMES_KEY: commonNames,  VAR_NAMES_UNIQUE_TO_A_KEY: uniqueToANames, VAR_NAMES_UNIQUE_TO_B_KEY: uniqueToBNames}

def resolve_names(fileAObject, fileBObject, defaultValues,
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
    nameComparison = _check_shared_names(set(fileAObject()), set(fileBObject()))
    
    # figure out which set should be selected based on the user requested names
    fileCommonNames = nameComparison[SHARED_VARIABLE_NAMES_KEY]
    finalNames = {}
    if (usingConfigFileFormat) :
        
        # if the user didn't ask for any, try everything
        if (len(requestedNames) is 0) :
            finalFromCommandLine = parse_varnames(fileCommonNames, ['.*'],
                                                  defaultValues[EPSILON_KEY], defaultValues[FILL_VALUE_KEY])
            for name, epsilon, missing in finalFromCommandLine :
                # we'll use the variable's name as the display name for the time being
                finalNames[name] = {}
                # make sure we pick up any other controlling defaults
                finalNames[name].update(defaultValues) 
                # but override the values that would have been determined by _parse_varnames
                finalNames[name][VARIABLE_TECH_NAME_KEY] = name
                finalNames[name][EPSILON_KEY] = epsilon
                
                # load the missing value if it was not provided
                missing, missing_b = _get_missing_values_if_needed((fileAObject, fileBObject), name,
                                                                   missing_value_A=missing, missing_value_B=missing)
                finalNames[name][FILL_VALUE_KEY]          = missing 
                finalNames[name][FILL_VALUE_ALT_IN_B_KEY] = missing_b
                
                # get any information about the units listed in the files
                finalNames[name][VAR_UNITS_A_KEY] = fileAObject.get_attribute(name, io.UNITS_CONSTANT)
                finalNames[name][VAR_UNITS_B_KEY] = fileBObject.get_attribute(name, io.UNITS_CONSTANT)
                
        # otherwise just do the ones the user asked for
        else : 
            # check each of the names the user asked for to see if it is either in the list of common names
            # or, if the user asked for an alternate name mapping in file B, if the two mapped names are in
            # files A and B respectively
            for dispName in requestedNames :
                
                # hang on to info on the current variable
                currNameInfo = requestedNames[dispName] 
                
                # get the variable name 
                if VARIABLE_TECH_NAME_KEY in currNameInfo :
                    name = currNameInfo[VARIABLE_TECH_NAME_KEY]
                    name_b = name
                    
                    if (VARIABLE_B_TECH_NAME_KEY in currNameInfo) :
                        name_b = currNameInfo[VARIABLE_B_TECH_NAME_KEY]
                    
                    if ( (name in fileCommonNames) and (not currNameInfo.has_key(VARIABLE_B_TECH_NAME_KEY)) ) or \
                            ( (currNameInfo.has_key(VARIABLE_B_TECH_NAME_KEY) and
                              ((name   in nameComparison[VAR_NAMES_UNIQUE_TO_A_KEY]) or (name   in fileCommonNames))  and
                              ((name_b in nameComparison[VAR_NAMES_UNIQUE_TO_B_KEY]) or (name_b in fileCommonNames))) ) :
                        finalNames[dispName] = defaultValues.copy() 
                        finalNames[dispName][DISPLAY_NAME_KEY] = dispName
                        finalNames[dispName].update(currNameInfo)
                        
                        # load the missing value if it was not provided
                        missing   = finalNames[dispName][FILL_VALUE_KEY]
                        missing_b = finalNames[dispName][FILL_VALUE_ALT_IN_B_KEY] if (FILL_VALUE_ALT_IN_B_KEY in finalNames[dispName]) else missing
                        finalNames[dispName][FILL_VALUE_KEY], finalNames[dispName][FILL_VALUE_ALT_IN_B_KEY] = \
                                    _get_missing_values_if_needed((fileAObject, fileBObject), name, name_b,
                                                                  missing, missing_b)
                        
                        # get any information about the units listed in the files
                        finalNames[dispName][VAR_UNITS_A_KEY] = fileAObject.get_attribute(name,   io.UNITS_CONSTANT)
                        finalNames[dispName][VAR_UNITS_B_KEY] = fileBObject.get_attribute(name_b, io.UNITS_CONSTANT)
                        
                else :
                    LOG.warn('No technical variable name was given for the entry described as "' + dispName + '". ' +
                             'Skipping this variable.')
    else:
        # format command line input similarly to the stuff from the config file
        #print (requestedNames)
        finalFromCommandLine = parse_varnames(fileCommonNames, requestedNames,
                                              defaultValues[EPSILON_KEY], defaultValues[FILL_VALUE_KEY])
        for name, epsilon, missing in finalFromCommandLine :
            ## we'll use the variable's name as the display name for the time being
            finalNames[name] = {}
            # make sure we pick up any other controlling defaults
            finalNames[name].update(defaultValues) 
            # but override the values that would have been determined by _parse_varnames
            finalNames[name][VARIABLE_TECH_NAME_KEY] = name
            finalNames[name][EPSILON_KEY]            = epsilon
            
            # load the missing value if it was not provided
            missing, missing_b = _get_missing_values_if_needed((fileAObject, fileBObject), name,
                                                               missing_value_A=missing, missing_value_B=missing)
            finalNames[name][FILL_VALUE_KEY]          = missing 
            finalNames[name][FILL_VALUE_ALT_IN_B_KEY] = missing_b
            
            # get any information about the units listed in the files
            finalNames[name][VAR_UNITS_A_KEY] = fileAObject.get_attribute(name, io.UNITS_CONSTANT)
            finalNames[name][VAR_UNITS_B_KEY] = fileBObject.get_attribute(name, io.UNITS_CONSTANT)
    
    LOG.debug("Final selected set of variables to analyze:")
    LOG.debug(str(finalNames))
    
    return finalNames, nameComparison

def resolve_names_one_file(fileObject, defaultValues,
                           requestedNames, usingConfigFileFormat=False) :
    """
    sort out which names to examine based on a file that contains names and the names
    the caller asked for, then fill in information on missing values based on the
    caller requests, possible config file, and defaults
    """
    # look at the names present in the file
    possibleNames = set(fileObject())
    
    # figure out which names should be selected based on the user requested names
    finalNames = {}
    if (usingConfigFileFormat) :
        
        # if the user didn't ask for any, try everything
        if (len(requestedNames) is 0) :
            finalFromCommandLine = parse_varnames(possibleNames, ['.*'],
                                                  None, defaultValues[FILL_VALUE_KEY])
            for name, _, missing in finalFromCommandLine :
                # we'll use the variable's name as the display name for the time being
                finalNames[name] = {}
                # make sure we pick up any other controlling defaults
                finalNames[name].update(defaultValues) 
                # but override the values that would have been determined by _parse_varnames
                finalNames[name][VARIABLE_TECH_NAME_KEY] = name
                
                # load the missing value if it was not provided
                missing = fileObject.missing_value(name) if (missing is None) else missing
                finalNames[name][FILL_VALUE_KEY] = missing
                
                # get any information about the units listed in the file
                finalNames[name][VAR_UNITS_A_KEY] = fileObject.get_attribute(name, io.UNITS_CONSTANT)
                
        # otherwise just do the ones the user asked for
        else : 
            # check each of the names the user asked for to see if it's among the possible names
            for dispName in requestedNames :
                
                # hang on to info on the current variable
                currNameInfo = requestedNames[dispName] 
                
                # get the variable name 
                if VARIABLE_TECH_NAME_KEY in currNameInfo :
                    name = currNameInfo[VARIABLE_TECH_NAME_KEY]
                    
                    if (name in possibleNames) :
                        finalNames[dispName] = defaultValues.copy() 
                        finalNames[dispName][DISPLAY_NAME_KEY] = dispName
                        finalNames[dispName].update(currNameInfo)
                        
                        # load the missing value if it was not provided
                        missing = finalNames[dispName][FILL_VALUE_KEY]
                        if missing is None :
                            missing = fileObject.missing_value(name)
                        finalNames[dispName][FILL_VALUE_KEY] = missing
                        
                        # get any information about the units listed in the file
                        finalNames[dispName][VAR_UNITS_A_KEY] = fileObject.get_attribute(name, io.UNITS_CONSTANT)
                        
                else :
                    LOG.warn('No technical variable name was given for the entry described as "' + dispName + '". ' +
                             'Skipping this variable.')
    else:
        # format command line input similarly to the stuff from the config file
        #print (requestedNames)
        finalFromCommandLine = parse_varnames(possibleNames, requestedNames,
                                              None, defaultValues[FILL_VALUE_KEY])
        for name, _, missing in finalFromCommandLine :
            ## we'll use the variable's name as the display name for the time being
            finalNames[name] = {}
            # make sure we pick up any other controlling defaults
            finalNames[name].update(defaultValues) 
            # but override the values that would have been determined by _parse_varnames
            finalNames[name][VARIABLE_TECH_NAME_KEY] = name
            
            # load the missing value if it was not provided
            if missing is None :
                missing = fileObject.missing_value(name)
            finalNames[name][FILL_VALUE_KEY] = missing
            
            # get any information about the units listed in the file
            finalNames[name][VAR_UNITS_A_KEY] = fileObject.get_attribute(name, io.UNITS_CONSTANT)
    
    LOG.debug("Final selected set of variables to inspect:")
    LOG.debug(str(finalNames))
    
    return finalNames, possibleNames

def _get_missing_values_if_needed((fileA, fileB),
                                  var_name, alt_var_name=None, 
                                  missing_value_A=None, missing_value_B=None) :
    """
    get the missing values for two files based on the variable name(s)
    if the alternate variable name is passed it will be used for the
    second file in place of the primary variable name
    """
    # if we don't have an alternate variable name, use the existing one
    if alt_var_name is None :
        alt_var_name = var_name
    
    if missing_value_A is None :
        missing_value_A = fileA.missing_value(var_name)
    
    if missing_value_B is None :
        missing_value_B = fileB.missing_value(alt_var_name)
    
    return missing_value_A, missing_value_B

# TODO, right now this is the top level function that the library functions in
# compare.py call
def load_config_or_options(aPath, bPath, optionsSet, requestedVars = [ ]) :
    """
    load information on how the user wants to run the command from a dictionary of options 
    and info on the files and variables to compare
    note: the options may include a configuration file, which will override many of the
    settings in the options
    """
    
    # basic defaults for stuff we will need to return
    runInfo = {}
    runInfo.update(glance_setting_defaults) # get the default settings
    if (USE_NO_LON_OR_LAT_VARS_KEY not in optionsSet) or (not optionsSet[USE_NO_LON_OR_LAT_VARS_KEY]):
        runInfo.update(glance_lon_lat_defaults) # get the default lon/lat info
    
    # by default, we don't have any particular variables to analyze
    desiredVariables = { }
    # use the built in default values, to start with
    defaultsToUse = glance_analysis_defaults.copy()
    
    requestedNames = None
    
    # set up the paths, they can only come from the command line
    paths = {}
    paths[A_FILE_KEY]     = aPath
    if bPath is not None:
        paths[B_FILE_KEY] = bPath
    paths[OUT_FILE_KEY] = optionsSet[OPTIONS_OUTPUT_PATH_KEY]
    
    # the colocation selection can only come from the command line options
    # note: since this is really only coming from the user's selection of the call,
    # this is ok for the moment, may want to reconsider later (FUTURE)
    runInfo[DO_COLOCATION_KEY] = (DO_COLOCATION_KEY in optionsSet) and (optionsSet[DO_COLOCATION_KEY])
    
    # check to see if the user wants to use a config file and if the path exists
    requestedConfigFile = optionsSet[OPTIONS_CONFIG_FILE_KEY]
    usedConfigFile      = False
    if (requestedConfigFile is not None) and (requestedConfigFile != "") :
        if not os.path.exists(requestedConfigFile) :
            LOG.warn("Could not open config file: \"" + requestedConfigFile + "\"")
            LOG.warn("Unable to continue analysis without selected configuration file.")
            sys.exit(1)
            
        else :
            
            LOG.info ("Using Config File Settings")
            
            # this will handle relative paths
            requestedConfigFile = os.path.abspath(os.path.expanduser(requestedConfigFile))
            
            # split out the file base name and the file path
            (filePath, fileName) = os.path.split(requestedConfigFile)
            splitFileName = fileName.split('.')
            fileBaseName = fileName[:-3] # remove the '.py' from the end
            
            # hang onto info about the config file for later
            runInfo[CONFIG_FILE_NAME_KEY] = fileName
            runInfo[CONFIG_FILE_PATH_KEY] = requestedConfigFile
            
            # load the file
            LOG.debug ('loading config file: ' + str(requestedConfigFile))
            glanceRunConfig = imp.load_module(fileBaseName, file(requestedConfigFile, 'U'),
                                              filePath, ('.py' , 'U', 1))
            
            # this is an exception, since it is not advertised to the user we don't expect it to be in the file
            # (at least not at the moment, it could be added later and if they did happen to put it in the
            # config file, it would override this line)
            runInfo[DO_MAKE_REPORT_KEY]         = not optionsSet[OPTIONS_NO_REPORT_KEY]      if OPTIONS_NO_REPORT_KEY      in optionsSet else False
            runInfo[USE_NO_LON_OR_LAT_VARS_KEY] =     optionsSet[USE_NO_LON_OR_LAT_VARS_KEY] if USE_NO_LON_OR_LAT_VARS_KEY in optionsSet else False
            
            # get everything from the config file
            runInfo.update(glanceRunConfig.settings)
            if (USE_NO_LON_OR_LAT_VARS_KEY not in runInfo) or (not runInfo[USE_NO_LON_OR_LAT_VARS_KEY]) :
                runInfo.update(glanceRunConfig.lat_lon_info) # get info on the lat/lon variables
            
            # get any requested names
            requestedNames = glanceRunConfig.setOfVariables.copy()
            # user selected defaults, if they omit any we'll still be using the program defaults
            defaultsToUse.update(glanceRunConfig.defaultValues)
            
            usedConfigFile = True
    
    # if we didn't get the info from the config file for some reason
    # (the user didn't want to, we couldn't, etc...) get it from the command line options
    if not usedConfigFile:
        
        LOG.info ('Using Command Line Settings')
        
        # so get everything from the options directly
        runInfo[DO_MAKE_REPORT_KEY] = not optionsSet[OPTIONS_NO_REPORT_KEY]
        runInfo[DO_MAKE_IMAGES_KEY] = not optionsSet[OPTIONS_NO_IMAGES_KEY]
        runInfo[DO_MAKE_FORKS_KEY]  =     optionsSet[DO_MAKE_FORKS_KEY]
        
        # only record these if we are using lon/lat
        runInfo[USE_NO_LON_OR_LAT_VARS_KEY] = optionsSet[USE_NO_LON_OR_LAT_VARS_KEY]
        if not runInfo[USE_NO_LON_OR_LAT_VARS_KEY] :
            runInfo[LATITUDE_NAME_KEY]   = optionsSet[OPTIONS_LAT_VAR_NAME_KEY] or runInfo[LATITUDE_NAME_KEY]
            runInfo[LONGITUDE_NAME_KEY]  = optionsSet[OPTIONS_LON_VAR_NAME_KEY] or runInfo[LONGITUDE_NAME_KEY]
            runInfo[LON_LAT_EPSILON_KEY] = optionsSet[OPTIONS_LONLAT_EPSILON_KEY] if OPTIONS_LONLAT_EPSILON_KEY in optionsSet else None
        
        # get any requested names from the command line
        requestedNames = requestedVars or ['.*'] 
        
        # user selected defaults
        defaultsToUse[EPSILON_KEY]    = optionsSet[EPSILON_KEY] if EPSILON_KEY in optionsSet else None
        defaultsToUse[FILL_VALUE_KEY] = optionsSet[OPTIONS_FILL_VALUE_KEY]
        
        # note: there is no way to set the tolerances from the command line
    
    return paths, runInfo, defaultsToUse, requestedNames, usedConfigFile

def set_up_command_line_options (parser) :
    """
    given an optparse.OptionParser object, set the appropriate options for glance's command line
    """
    
    # option to run a test
    parser.add_option('-t', '--test', dest="self_test",
                    action="store_true", default=False, help="run internal unit tests")
    
    # message related options
    parser.add_option('-q', '--quiet', dest="quiet",
                    action="store_true", default=False, help="only error output")
    parser.add_option('-v', '--verbose', dest="verbose",
                    action="store_true", default=False, help="enable more informational output")   
    parser.add_option('-w', '--debug', dest="debug",
                    action="store_true", default=False, help="enable debug output")
    parser.add_option('-n', '--version', dest='version',
                      action="store_true", default=False, help="view the glance version")
    
    # data options for setting variable defaults
    parser.add_option('-e', '--epsilon', dest=EPSILON_KEY, type='float', default=0.0,
                    help="set default epsilon value for comparison threshold")   
    parser.add_option('-m', '--missing', dest=OPTIONS_FILL_VALUE_KEY, type='float', default=None,
                    help="set default missing-value")
    
    # longitude and latitude related options
    parser.add_option('-o', '--longitude', dest=OPTIONS_LON_VAR_NAME_KEY, type='string',
                    help="set name of longitude variable")
    parser.add_option('-a', '--latitude', dest=OPTIONS_LAT_VAR_NAME_KEY, type='string',
                    help="set name of latitude variable")
    parser.add_option('-l', '--llepsilon', dest=OPTIONS_LONLAT_EPSILON_KEY, type='float', default=0.0,
                      help="set default epsilon for longitude and latitude comparsion")
    parser.add_option('-d', '--nolonlat', dest=USE_NO_LON_OR_LAT_VARS_KEY,
                      action="store_true", default=False, help="do not try to find or analyze logitude and latitude")
    
    # output generation related options
    parser.add_option('-p', '--outputpath', dest=OPTIONS_OUTPUT_PATH_KEY, type='string', default='./',
                    help="set path to output directory")
    parser.add_option('-i', '--imagesonly', dest=OPTIONS_NO_REPORT_KEY, 
                      action="store_true", default=False,
                      help="generate only image files (no html report)")
    parser.add_option('-r', '--reportonly', dest=OPTIONS_NO_IMAGES_KEY, 
                      action="store_true", default=False,
                      help="generate only html report files (no images)")
    parser.add_option('-c', '--configfile', dest=OPTIONS_CONFIG_FILE_KEY, type='string', default=None,
                      help="set optional configuration file")
    parser.add_option('--fields', type='string',
                      default='filename,variable',
                      help="comma separted list of additional fields to add to info's output")
    
    # should pass/fail be tested?
    parser.add_option('-x', '--doPassFail', dest=DO_TEST_PASSFAIL_KEY,
                      action="store_true", default=False, help="should the comparison test for pass/fail (currently only affects stats)")
    
    # whether or not to do multiprocessing
    parser.add_option('-f', '--fork', dest=DO_MAKE_FORKS_KEY,
                      action="store_true", default=False, help="start multiple processes to create images in parallel")

    parser.add_option('--parsable', dest=PARSABLE_OUTPUT_KEY,
                      action="store_true", default=False, help="format output to be programmatically parsed. 'info' only")

def convert_options_to_dict (options) :
    """
    convert the command line options structure created in compare.py into a dictionary of values
    that can be easily parsed later
    
    num_expected_file_paths represents the number of file paths we expect the user to have entered
    at the command line... if we can't find arguments that are plausibly those file paths, we
    will consider the attempt to convert the options a failure
    """
    
    tempOptions = { }
    
    # variable defaults
    tempOptions[EPSILON_KEY]                = options.epsilon
    tempOptions[OPTIONS_FILL_VALUE_KEY]     = options.missing
    
    # lon/lat options
    tempOptions[OPTIONS_LAT_VAR_NAME_KEY]   = options.latitudeVar
    tempOptions[OPTIONS_LON_VAR_NAME_KEY]   = options.longitudeVar
    tempOptions[OPTIONS_LONLAT_EPSILON_KEY] = options.lonlatepsilon
    tempOptions[USE_NO_LON_OR_LAT_VARS_KEY] = options.noLonLatVars
    
    # in/out file related options
    tempOptions[OPTIONS_OUTPUT_PATH_KEY]    = clean_path(options.outputpath)
    tempOptions[OPTIONS_CONFIG_FILE_KEY]    = clean_path(options.configFile)
    tempOptions[OPTIONS_NO_REPORT_KEY]      = options.imagesOnly
    tempOptions[OPTIONS_NO_IMAGES_KEY]      = options.htmlOnly
    
    # whether or not to do pass fail testing
    tempOptions[DO_TEST_PASSFAIL_KEY]       = options.usePassFail
    
    # whether or not to do multiprocessing
    tempOptions[DO_MAKE_FORKS_KEY]          = options.doFork
    
    return tempOptions

def get_simple_options_dict ( ) :
    """
    get a simple version of the options dictionary without any input from the command line
    """
    
    # set up the run info
    tempOptions = { }
    tempOptions.update(glance_setting_defaults)
    
    return tempOptions

def get_simple_variable_defaults ( ) :
    
    tempOptions = { }
    tempOptions.update(glance_analysis_defaults)
    
    return tempOptions

# FUTURE, at some point set up test cases
if __name__=='__main__':
    
    LOG.info("Currently no tests are configured for this module.")
    
    sys.exit(0)
