#!/usr/bin/env python
# encoding: utf-8
"""

Top-level routines to compare two files.


Created by rayg Apr 2009.
Copyright (c) 2009 University of Wisconsin SSEC. All rights reserved.
"""

#from pprint import pprint, pformat

import os, sys, logging, re, datetime
from numpy import *
from urllib import quote

import matplotlib
# this is a hack to keep glance from needing pyqt unless you run the gui
if "gui" in sys.argv[1:] :
    try :
        matplotlib.use('Qt4Agg')
        import glance.gui_controller as gui_control
    except ImportError :
        print ("*** Unable to import PyQt4. Please install PyQt4 and add it to your PYTHONPATH in order to use the Glance GUI. ***")
        raise
else :
    matplotlib.use('Agg')

import glance.io     as io
import glance.data   as dataobj
import glance.report as report
import glance.stats  as statistics
import glance.plot   as plot
import glance.plotcreatefns as plotcreate
import glance.collocation   as collocation
import glance.config_organizer as config_organizer

from glance.util        import clean_path, rsync_or_copy_files, get_glance_version_string, get_run_identification_info, setup_dir_if_needed
from glance.load        import get_UV_info_from_magnitude_direction_info, load_variable_data, open_and_process_files, handle_lon_lat_info, handle_lon_lat_info_for_one_file
from glance.lonlat_util import VariableComparisonError
from glance.constants   import *
from glance.gui_constants import A_CONST, B_CONST

LOG = logging.getLogger(__name__)

# TODO, I'd like to move this into a different file at some point
def _get_name_info_for_variable(original_display_name, variable_run_info) :
    """
    based on the variable run info, figure out the various names for
    the variable and return them
    
    the various names are:
    
    technical_name -            the name the variable is listed under in the file
    b_variable_technical_name - the name the variable is listed under in the b file (may be the same as technical_name)
    explanation_name -          the more verbose name that will be shown to the user to identify the variable
    original_display_name -     the display name given by the user to describe the variable
    """
    
    # figure out the various name related info
    technical_name = variable_run_info[VARIABLE_TECH_NAME_KEY]
    explanation_name = technical_name # for now, will add to this later
    
    # if B has an alternate variable name, figure that out
    b_variable_technical_name = technical_name
    if VARIABLE_B_TECH_NAME_KEY in variable_run_info :
        b_variable_technical_name = variable_run_info[VARIABLE_B_TECH_NAME_KEY]
        # put both names in our explanation
        explanation_name = explanation_name + " / " + b_variable_technical_name
    
    # show both the display and current explanation names if they differ
    if not (original_display_name == explanation_name) :
        explanation_name = original_display_name + ' (' + explanation_name + ')'
    
    return technical_name, b_variable_technical_name, explanation_name

def colocateToFile_library_call(a_path, b_path, var_list=[ ],
                                options_set={ },
                                # todo, this doesn't yet do anything
                                do_document=False,
                                # todo, the output channel does nothing at the moment
                                output_channel=sys.stdout) :
    """
    this method handles the actual work of the colocateData command line tool
    and can be used as a library routine.
    
    TODO, properly document the options
    """
    
    # load the user settings from either the command line or a user defined config file
    pathsTemp, runInfo, defaultValues, requestedNames, usedConfigFile = config_organizer.load_config_or_options(a_path, b_path,
                                                                                                                options_set,
                                                                                                                requestedVars = var_list)
    
    # deal with the input and output files
    setup_dir_if_needed(pathsTemp[OUT_FILE_KEY], "output")
    
    # make copies of the input files for colocation TODO, fix paths
    [pathsTemp[A_FILE_KEY], pathsTemp[B_FILE_KEY]] = rsync_or_copy_files ([pathsTemp[A_FILE_KEY], pathsTemp[B_FILE_KEY]],
                                                                          target_directory=pathsTemp[OUT_FILE_KEY],
                                                                          additionalFileNameSuffix='-collocated')
    
    # open the files
    LOG.info("Processing File A:")
    aFile = dataobj.FileInfo(pathsTemp[A_FILE_KEY], allowWrite=True)
    if aFile is None:
        LOG.warn("Unable to continue with comparison because file a (" + pathsTemp[A_FILE_KEY] + ") could not be opened.")
        sys.exit(1)
    LOG.info("Processing File B:")
    bFile = dataobj.FileInfo(pathsTemp[B_FILE_KEY], allowWrite=True)
    if bFile is None:
        LOG.warn("Unable to continue with comparison because file b (" + pathsTemp[B_FILE_KEY] + ") could not be opened.")
        sys.exit(1)
    
    # get information about the names the user requested
    finalNames, nameStats = config_organizer.resolve_names(aFile.file_object,
                                                           bFile.file_object,
                                                           defaultValues,
                                                           requestedNames,
                                                           usedConfigFile)
    
    # return for lon_lat_data variables will be in the form 
    #{LON_KEY: longitude_data,      LAT_KEY: latitude_data,      INVALID_MASK_KEY: spaciallyInvalidMaskData}
    # or { } if there is no lon/lat info
    lon_lat_data = { }
    try :
        lon_lat_data, _ = handle_lon_lat_info (runInfo, aFile, bFile, pathsTemp[OUT_FILE_KEY], should_check_equality=False,
                                               fullDPI=runInfo[DETAIL_DPI_KEY], thumbDPI=runInfo[THUMBNAIL_DPI_KEY])
    except ValueError, vle :
        LOG.warn("Error while loading longitude or latitude: ")
        LOG.warn(str(vle))
        exit(1)
    except VariableComparisonError, vce :
        LOG.warn("Error while comparing longitude or latitude: ")
        LOG.warn(str(vce))
        exit(1)
    
    # handle the longitude and latitude colocation
    LOG.info("Colocating raw longitude and latitude information")
    aColocationInfomation, bColocationInformation, totalNumberOfMatchedPoints = \
                    collocation.create_colocation_mapping_within_epsilon((lon_lat_data[A_FILE_KEY][LON_KEY], lon_lat_data[A_FILE_KEY][LAT_KEY]),
                                                                         (lon_lat_data[B_FILE_KEY][LON_KEY], lon_lat_data[B_FILE_KEY][LAT_KEY]),
                                                                         runInfo[LON_LAT_EPSILON_KEY],
                                                                         invalidAMask=lon_lat_data[A_FILE_KEY][INVALID_MASK_KEY],
                                                                         invalidBMask=lon_lat_data[B_FILE_KEY][INVALID_MASK_KEY])
    (colocatedLongitude, colocatedLatitude, (numMultipleMatchesInA, numMultipleMatchesInB)), \
    (unmatchedALongitude, unmatchedALatitude), \
    (unmatchedBLongitude, unmatchedBLatitude) = \
                collocation.create_colocated_lonlat_with_lon_lat_colocation(aColocationInfomation, bColocationInformation,
                                                                            totalNumberOfMatchedPoints,
                                                                            lon_lat_data[A_FILE_KEY][LON_KEY], lon_lat_data[A_FILE_KEY][LAT_KEY],
                                                                            lon_lat_data[B_FILE_KEY][LON_KEY], lon_lat_data[B_FILE_KEY][LAT_KEY])
    
    # TODO, based on unmatched, issue warnings and record info in the file?
    LOG.debug("colocated shape of the longitude: " + str(colocatedLongitude.shape))
    LOG.debug("colocated shape of the latitude:  " + str(colocatedLatitude.shape))
    LOG.debug(str(numMultipleMatchesInA) + " lon/lat pairs contain A points used for multiple matches.")
    LOG.debug(str(numMultipleMatchesInB) + " lon/lat pairs contain B points used for multiple matches.")
    LOG.debug(str(len(unmatchedALatitude)) + " A lon/lat points could not be matched.")
    LOG.debug(str(len(unmatchedBLatitude)) + " B lon/lat points could not be matched.")
    
    # go through each of the possible variables in our files
    # and do our colocation for whichever ones we can
    for displayName in finalNames:
        
        # pull out the information for this variable analysis run
        varRunInfo = finalNames[displayName].copy()
        
        # get the various names
        technical_name, b_variable_technical_name, \
                explanationName = _get_name_info_for_variable(displayName, varRunInfo)
        
        LOG.info('analyzing: ' + explanationName + ')')
        
        # load the variable data
        aData = load_variable_data(aFile.file_object, technical_name,
                                   dataFilter = varRunInfo[FILTER_FUNCTION_A_KEY] if FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   variableToFilterOn = varRunInfo[VAR_FILTER_NAME_A_KEY] if VAR_FILTER_NAME_A_KEY in varRunInfo else None,
                                   variableBasedFilter = varRunInfo[VAR_FILTER_FUNCTION_A_KEY] if VAR_FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   altVariableFileObject = dataobj.FileInfo(varRunInfo[VAR_FILTER_ALT_FILE_A_KEY]).file_object if VAR_FILTER_ALT_FILE_A_KEY in varRunInfo else None,
                                   fileDescriptionForDisplay = "file A")
        bData = load_variable_data(bFile.file_object, b_variable_technical_name,
                                   dataFilter = varRunInfo[FILTER_FUNCTION_B_KEY] if FILTER_FUNCTION_B_KEY in varRunInfo else None,
                                   variableToFilterOn = varRunInfo[VAR_FILTER_NAME_B_KEY] if VAR_FILTER_NAME_B_KEY in varRunInfo else None,
                                   variableBasedFilter = varRunInfo[VAR_FILTER_FUNCTION_B_KEY] if VAR_FILTER_FUNCTION_B_KEY in varRunInfo else None,
                                   altVariableFileObject = dataobj.FileInfo(varRunInfo[VAR_FILTER_ALT_FILE_B_KEY]).file_object if VAR_FILTER_ALT_FILE_B_KEY in varRunInfo else None,
                                   fileDescriptionForDisplay = "file B")
        
        # colocate the data for this variable if we have longitude/latitude data
        if (len(lon_lat_data.keys()) > 0) and runInfo[DO_COLOCATION_KEY] :
            
            # figure out the invalid masks
            invalidA = lon_lat_data[A_FILE_KEY][INVALID_MASK_KEY] | (aData == varRunInfo[FILL_VALUE_KEY])
            invalidB = lon_lat_data[B_FILE_KEY][INVALID_MASK_KEY] | (bData == varRunInfo[FILL_VALUE_ALT_IN_B_KEY])
            
            # match up our points in A and B
            (aData, bData, (numberOfMultipleMatchesInA, numberOfMultipleMatchesInB)), \
            (aUnmatchedData,             unmatchedALongitude, unmatchedALatitude), \
            (bUnmatchedData,             unmatchedBLongitude, unmatchedBLatitude) = \
                    collocation.create_colocated_data_with_lon_lat_colocation(aColocationInfomation, bColocationInformation,
                                                                              colocatedLongitude, colocatedLatitude,
                                                                              aData, bData,
                                                                              missingData=varRunInfo[FILL_VALUE_KEY],
                                                                              altMissingDataInB=varRunInfo[FILL_VALUE_ALT_IN_B_KEY],
                                                                              invalidAMask=invalidA,
                                                                              invalidBMask=invalidB)
            
            LOG.debug(str(numberOfMultipleMatchesInA) + " data pairs contain A data points used for multiple matches.")
            LOG.debug(str(numberOfMultipleMatchesInB) + " data pairs contain B data points used for multiple matches.")
            LOG.debug(str(len(aUnmatchedData)) + " A data points could not be matched.")
            LOG.debug(str(len(bUnmatchedData)) + " B data points could not be matched.")
            
            # save the colocated data information in the output files
            
            # all the a file information
            aFile.file_object.create_new_variable(technical_name + '-colocated', # TODO, how should this suffix be handled?
                                      missingvalue = varRunInfo[FILL_VALUE_KEY] if FILL_VALUE_KEY in varRunInfo else None,
                                      data = aData,
                                      variabletocopyattributesfrom = technical_name)
            aFile.file_object.add_attribute_data_to_variable(technical_name + '-colocated', 'number of multiple matches', numberOfMultipleMatchesInA)
            aFile.file_object.add_attribute_data_to_variable(technical_name + '-colocated', 'number of unmatched points', len(aUnmatchedData))
            
            # all the b file information
            bFile.file_object.create_new_variable(b_variable_technical_name + '-colocated', # TODO, how should this suffix be handled?
                                      missingvalue = varRunInfo[FILL_VALUE_ALT_IN_B_KEY] if FILL_VALUE_ALT_IN_B_KEY in varRunInfo else None,
                                      data = bData,
                                      variabletocopyattributesfrom = b_variable_technical_name)
            bFile.file_object.add_attribute_data_to_variable(b_variable_technical_name + '-colocated', 'number of multiple matches', numberOfMultipleMatchesInB)
            bFile.file_object.add_attribute_data_to_variable(b_variable_technical_name + '-colocated', 'number of unmatched points', len(bUnmatchedData))
            
            # TODO, any additional statistics
            
        else :
            LOG.debug(explanationName + " was not selected for colocation and will be ignored.")
        
    # the end of the loop to examine all the variables
    
    # we're done with the files, so close them up
    aFile.file_object.close()
    bFile.file_object.close()
    
    return

def reportGen_raw_data_simple_call (aData, bData, variableDisplayName,
                                    epsilon=0.0, missingValue=None,
                                    useThreads=True, includeImages=True,
                                    outputDirectory="./") :
    """
    Generate a report for a single variable given raw data and
    some minimal control settings. This method will also generate
    images for the report if includeImages is True.
    """
    
    LOG.info("Setting up basic information")
    
    aData = array(aData)
    bData = array(bData)
    
    # set up the run info
    runInfo = config_organizer.get_simple_options_dict( )
    runInfo[DO_MAKE_IMAGES_KEY]        = True
    runInfo[DO_MAKE_REPORT_KEY]        = True
    runInfo[DO_MAKE_FORKS_KEY]         = False
    runInfo[DO_CLEAR_MEM_THREADED_KEY] = useThreads
    
    # set up the variable specific info
    variableSettings = config_organizer.get_simple_variable_defaults( )
    variableSettings[EPSILON_KEY]             = epsilon
    variableSettings[FILL_VALUE_KEY]          = missingValue
    variableSettings[FILL_VALUE_ALT_IN_B_KEY] = missingValue
    variableSettings[VARIABLE_TECH_NAME_KEY]  = variableDisplayName
    
    # hang onto identification info
    runInfo[MACHINE_INFO_KEY], runInfo[USER_INFO_KEY], runInfo[GLANCE_VERSION_INFO_KEY] = get_run_identification_info()
    
    # deal with the output directories
    outputDirectory = clean_path(outputDirectory)
    setup_dir_if_needed(outputDirectory, "output")
    
    LOG.info("Analyzing " + variableDisplayName)
    
    # if things are the same shape, analyze them and make our images
    if aData.shape == bData.shape :
        
        # setup some values in the variable settings for use in the report
        variableSettings[VARIABLE_DIRECTORY_KEY] = outputDirectory
        variableSettings[VAR_REPORT_PATH_KEY]    = quote(os.path.join(variableDisplayName, 'index.html'))
        variableSettings[DOCUMENTATION_PATH_KEY] = quote(os.path.join(outputDirectory, './' + 'doc.html')) 
        
        # calculate the variable statistics
        variable_stats = statistics.StatisticalAnalysis.withSimpleData(aData, bData,
                                                                       missingValue, missingValue,
                                                                       None, None,
                                                                       epsilon, None)
        
        # add a little additional info
        variableSettings[TIME_INFO_KEY] = datetime.datetime.ctime(datetime.datetime.now()) # TODO, move this to util?
        didPass, epsilon_failed_fraction, \
        non_finite_fail_fraction, r_squared_value \
            = variable_stats.check_pass_or_fail(epsilon_failure_tolerance=variableSettings[EPSILON_FAIL_TOLERANCE_KEY] if EPSILON_FAIL_TOLERANCE_KEY in variableSettings else numpy.nan,
                                                epsilon_failure_tolerance_default=runInfo[EPSILON_FAIL_TOLERANCE_KEY],
                                                non_finite_data_tolerance=variableSettings[NONFINITE_TOLERANCE_KEY]  if NONFINITE_TOLERANCE_KEY  in variableSettings else numpy.nan,
                                                non_finite_data_tolerance_default=runInfo[NONFINITE_TOLERANCE_KEY],
                                                total_data_failure_tolerance=variableSettings[TOTAL_FAIL_TOLERANCE_KEY] if TOTAL_FAIL_TOLERANCE_KEY in variableSettings else numpy.nan,
                                                total_data_failure_tolerance_default=runInfo[TOTAL_FAIL_TOLERANCE_KEY],
                                                min_acceptable_r_squared=variableSettings[MIN_OK_R_SQUARED_COEFF_KEY] if MIN_OK_R_SQUARED_COEFF_KEY in variableSettings else numpy.nan,
                                                min_acceptable_r_squared_default=runInfo[MIN_OK_R_SQUARED_COEFF_KEY],
                                                )
        variableSettings[DID_VARIABLE_PASS_KEY] = didPass
        
        # to hold the names of any images created
        image_names = {
                        ORIGINAL_IMAGES_KEY: [ ],
                        COMPARED_IMAGES_KEY: [ ]
                        }
        
        # if we need the images, make them now
        if includeImages :
            
            LOG.info("Plotting images for " + variableDisplayName)
            
            plotFunctionGenerationObjects = [ ]
            
            # add the function to make the histogram and scatter plot
            plotFunctionGenerationObjects.append(plotcreate.BasicComparisonPlotsFunctionFactory())
            
            # add the function to do basic imshow images
            plotFunctionGenerationObjects.append(plotcreate.IMShowPlotFunctionFactory())
            
            # plot our lon/lat related info
            image_names[ORIGINAL_IMAGES_KEY], image_names[COMPARED_IMAGES_KEY] = \
                plot.plot_and_save_comparison_figures \
                        (aData, bData,
                         plotFunctionGenerationObjects,
                         outputDirectory,
                         variableDisplayName,
                         epsilon,
                         missingValue,
                         lonLatDataDict=None,
                         makeSmall=True,
                         doFork=False,
                         shouldClearMemoryWithThreads=useThreads,
                         shouldUseSharedRangeForOriginal=True)
            
            LOG.info("\tfinished creating figures for: " + variableDisplayName)
        
        # create a temporary files object
        files = {
                 A_FILE_TITLE_KEY: {
                                    PATH_KEY:          "raw data input",
                                    LAST_MODIFIED_KEY: "unknown",
                                    MD5SUM_KEY:        "n/a"
                                    },
                 B_FILE_TITLE_KEY: {
                                    PATH_KEY:          "raw data input",
                                    LAST_MODIFIED_KEY: "unknown",
                                    MD5SUM_KEY:        "n/a"
                                    }
                }
        
        # create our report 
        LOG.info ('Generating report for: ' + variableDisplayName) 
        report.generate_and_save_variable_report(files,
                                                 variableSettings, runInfo,
                                                 variable_stats.dictionary_form(),
                                                 { },
                                                 image_names,
                                                 outputDirectory, "index.html")
        
        # make the glossary page
        LOG.info ('Generating glossary page')
        report.generate_and_save_doc_page(statistics.StatisticalAnalysis.doc_strings(), outputDirectory)
        
    else :
        message = (variableDisplayName + ' ' + 
                'could not be compared. This may be because the data for this variable does not match in shape ' +
                'between the two files (file A data shape: ' + str(aData.shape) + '; file B data shape: '
                + str(bData.shape) + ').')
        LOG.warn(message)

def inspect_library_call (a_path, var_list=[ ],
                          options_set={ },
                          # todo, this doesn't yet do anything
                          do_document=False,
                          # todo, the output channel does nothing at the moment
                          output_channel=sys.stdout) :
    """
    this method handles the actual work of the inspectReport command line tool
    and can also be used as a library routine, pass in the slightly parsed
    command line input, or call it as a library function... be sure to fill
    out the options
    
    TODO at the moment the options are very brittle and need to be fully filled
    or this method will fail badly (note: the addition of some glance defaults
    has minimized the problem, but you still need to be careful when dealing with
    optional boolean values. this needs more work.)
    """
    
    # load the user settings from either the command line or a user defined config file
    pathsTemp, runInfo, defaultValues, requestedNames, usedConfigFile = config_organizer.load_config_or_options(a_path, None, # there is no B path
                                                                                                                options_set,
                                                                                                                requestedVars = var_list)
    
    # information for debugging purposes
    LOG.debug('paths: ' +           str(pathsTemp))
    LOG.debug('defaults: ' +        str(defaultValues))
    LOG.debug('run information: ' + str(runInfo))
    
    # if we wouldn't generate anything, just stop now
    if (not runInfo[DO_MAKE_IMAGES_KEY]) and (not runInfo[DO_MAKE_REPORT_KEY]) :
        LOG.warn("User selection of no image generation and no report generation will result in no " +
                 "content being generated. Aborting generation function.")
        return
    
    # hang onto info to identify who/what/when/where/etc. the report is being run by/for 
    runInfo[MACHINE_INFO_KEY], runInfo[USER_INFO_KEY], runInfo[GLANCE_VERSION_INFO_KEY] = get_run_identification_info()
    
    # deal with the input and output files
    setup_dir_if_needed(pathsTemp[OUT_FILE_KEY], "output")
    # open the file
    files = {}
    LOG.info("Processing File A:")
    aFile = dataobj.FileInfo(pathsTemp[A_FILE_KEY])
    files[A_FILE_TITLE_KEY] = aFile.get_old_info_dictionary() # FUTURE move to actually using the file object to generate the report
    if aFile.file_object is None:
        LOG.warn("Unable to continue with examination because file (" + pathsTemp[A_FILE_KEY] + ") could not be opened.")
        sys.exit(1)
    
    # get information about the names the user requested
    nameStats = {}
    finalNames, nameStats[POSSIBLE_NAMES_KEY] = config_organizer.resolve_names_one_file(aFile.file_object,
                                                                                        defaultValues, # TODO, might need a different default set
                                                                                        requestedNames,
                                                                                        usedConfigFile)
    
    LOG.debug("output dir: " + str(pathsTemp[OUT_FILE_KEY]))
    
    # return for lon_lat_data variables will be in the form 
    #{LON_KEY: longitude_data,      LAT_KEY: latitude_data,      INVALID_MASK_KEY: spaciallyInvalidMaskData}
    # or { } if there is no lon/lat info
    lon_lat_data = { }
    spatialInfo  = { }
    try :
        lon_lat_data, spatialInfo = handle_lon_lat_info_for_one_file (runInfo, aFile)
    except ValueError, vle :
        LOG.warn("Error while loading longitude or latitude: ")
        LOG.warn(str(vle))
        exit(1)
    
    # if there is an approved lon/lat shape, hang on to that for future variable data shape checks
    good_shape_from_lon_lat = None
    if len(lon_lat_data.keys()) > 0:
        good_shape_from_lon_lat = lon_lat_data[LON_KEY].shape
    
    # go through each of the possible variables in our files
    # and make a report section with images for whichever ones we can
    variableInspections = { }
    for displayName in finalNames:
        
        # pull out the information for this variable analysis run
        varRunInfo = finalNames[displayName].copy()
        
        # get the various names
        technical_name, _, explanationName = _get_name_info_for_variable(displayName, varRunInfo)
        
        # make sure that it's possible to load this variable
        if not(aFile.file_object.is_loadable_type(technical_name)) :
            LOG.warn(displayName + " is of a type that cannot be loaded using current file handling libraries included with Glance." +
                    " Skipping " + displayName + ".")
            continue
        
        LOG.info('analyzing: ' + explanationName)
        
        # load the variable data
        aData = load_variable_data(aFile.file_object, technical_name,
                                   dataFilter = varRunInfo[FILTER_FUNCTION_A_KEY] if FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   variableToFilterOn = varRunInfo[VAR_FILTER_NAME_A_KEY] if VAR_FILTER_NAME_A_KEY in varRunInfo else None,
                                   variableBasedFilter = varRunInfo[VAR_FILTER_FUNCTION_A_KEY] if VAR_FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   altVariableFileObject = dataobj.FileInfo(varRunInfo[VAR_FILTER_ALT_FILE_A_KEY]).file_object if VAR_FILTER_ALT_FILE_A_KEY in varRunInfo else None,
                                   fileDescriptionForDisplay = "file A")
        
        # pre-check if this data should be plotted and if it should be compared to the longitude and latitude
        include_images_for_this_variable = ((not(DO_MAKE_IMAGES_KEY in runInfo)) or (runInfo[DO_MAKE_IMAGES_KEY]))
        if DO_MAKE_IMAGES_KEY in varRunInfo :
            include_images_for_this_variable = varRunInfo[DO_MAKE_IMAGES_KEY]
        do_not_test_with_lon_lat = (not include_images_for_this_variable) or (len(lon_lat_data.keys()) <= 0)
        
        # handle vector data
        isVectorData = (MAGNITUDE_VAR_NAME_KEY in varRunInfo)  and (DIRECTION_VAR_NAME_KEY  in varRunInfo)
        
        # check if this data can be examined 
        # (don't compare lon/lat sizes if we won't be plotting)
        if ( do_not_test_with_lon_lat or (aData.shape == good_shape_from_lon_lat) ) :
            
            # check to see if there is a directory to put information about this variable in,
            # if not then create it
            variableDir = os.path.join(pathsTemp[OUT_FILE_KEY], './' + displayName)
            varRunInfo[VARIABLE_DIRECTORY_KEY] = variableDir
            varRunInfo[VAR_REPORT_PATH_KEY]    = quote(os.path.join(displayName, 'index.html'))
            LOG.debug ("Directory selected for variable information: " + varRunInfo[VAR_REPORT_PATH_KEY])
            setup_dir_if_needed(variableDir, "variable")
            
            # form the doc and config paths relative to where the variable is
            upwardPath = './'
            for number in range(len(displayName.split('/'))) : # TODO this is not general to windows
                upwardPath = os.path.join(upwardPath, '../')
            varRunInfo[DOCUMENTATION_PATH_KEY] = quote(os.path.join(upwardPath, 'doc.html'))
            if CONFIG_FILE_NAME_KEY in runInfo :
                varRunInfo[CONFIG_FILE_PATH_KEY] = quote(os.path.join(upwardPath, runInfo[CONFIG_FILE_NAME_KEY]))
            
            # figure out the masks we want, and then do our statistical analysis
            mask_a_to_use = None if do_not_test_with_lon_lat else lon_lat_data[INVALID_MASK_KEY]
            
            variable_stats = statistics.StatisticalInspectionAnalysis.withSimpleData(aData,
                                                                                     missingValue=varRunInfo[FILL_VALUE_KEY],
                                                                                     ignoreMask=mask_a_to_use).dictionary_form()
            
            # add a little additional info to our variable run info before we squirrel it away
            varRunInfo[TIME_INFO_KEY] = datetime.datetime.ctime(datetime.datetime.now())  # todo is this needed?
            
            # to hold the names of any images created
            image_names = {
                            ORIGINAL_IMAGES_KEY: [ ],
                            COMPARED_IMAGES_KEY: [ ]
                            }
            
            # create the images for this variable
            if (include_images_for_this_variable) :
                
                plotFunctionGenerationObjects = [ ]
                
                # we are always going to want to draw a basic histogram of the data values to tell which
                # occur most frequently
                plotFunctionGenerationObjects.append(plotcreate.DataHistogramPlotFunctionFactory())
                
                # if it's vector data with longitude and latitude, quiver plot it on the Earth
                if isVectorData and (not do_not_test_with_lon_lat) :
                    # TODO replace this at some point
                    #plotFunctionGenerationObjects.append(plotcreate.MappedQuiverPlotFunctionFactory())
                    pass
                
                # if the data is one dimensional we can plot it as lines
                elif   (len(aData.shape) is 1) : 
                    plotFunctionGenerationObjects.append(plotcreate.InspectLinePlotsFunctionFactory())
                
                # if the data is 2D we have some options based on the type of data
                elif (len(aData.shape) is 2) :
                    
                    # if the data is not mapped to a longitude and latitude, just show it as an image
                    if (do_not_test_with_lon_lat) :
                        plotFunctionGenerationObjects.append(plotcreate.InspectIMShowPlotFunctionFactory())
                    
                    # if it's 2D and mapped to the Earth, contour plot it on the earth
                    else :
                        plotFunctionGenerationObjects.append(plotcreate.InspectMappedContourPlotFunctionFactory())
                
                # if there's magnitude and direction data, figure out the u and v, otherwise these will be None
                aUData, aVData = get_UV_info_from_magnitude_direction_info (aFile.file_object,
                                                                            varRunInfo[MAGNITUDE_VAR_NAME_KEY] if (MAGNITUDE_VAR_NAME_KEY in varRunInfo)   else None,
                                                                            varRunInfo[DIRECTION_VAR_NAME_KEY] if (DIRECTION_VAR_NAME_KEY in varRunInfo)   else None,
                                                                            lon_lat_data[INVALID_MASK_KEY]     if (INVALID_MASK_KEY       in lon_lat_data) else None )
                
                # plot our images
                image_names[ORIGINAL_IMAGES_KEY], image_names[COMPARED_IMAGES_KEY] = \
                    plot.plot_and_save_comparison_figures \
                            (aData, None, # there is no b data
                             plotFunctionGenerationObjects,
                             varRunInfo[VARIABLE_DIRECTORY_KEY],
                             displayName,
                             None, # there is no epsilon
                             varRunInfo[FILL_VALUE_KEY],
                             lonLatDataDict=lon_lat_data,
                             dataRanges     = varRunInfo[DISPLAY_RANGES_KEY]       if DISPLAY_RANGES_KEY       in varRunInfo else None,
                             dataRangeNames = varRunInfo[DISPLAY_RANGE_NAMES_KEY]  if DISPLAY_RANGE_NAMES_KEY  in varRunInfo else None,
                             dataColors     = varRunInfo[DISPLAY_RANGE_COLORS_KEY] if DISPLAY_RANGE_COLORS_KEY in varRunInfo else None,
                             makeSmall=True,
                             doFork=runInfo[DO_MAKE_FORKS_KEY],
                             shouldClearMemoryWithThreads=runInfo[DO_CLEAR_MEM_THREADED_KEY],
                             shouldUseSharedRangeForOriginal=runInfo[USE_SHARED_ORIG_RANGE_KEY],
                             doPlotSettingsDict = varRunInfo,
                             aUData=aUData, aVData=aVData,
                             fullDPI=       runInfo[DETAIL_DPI_KEY],
                             thumbDPI=      runInfo[THUMBNAIL_DPI_KEY],
                             units_a=       varRunInfo[VAR_UNITS_A_KEY] if VAR_UNITS_A_KEY in varRunInfo else None,
                             useBData=False,
                             histRange=varRunInfo[HISTOGRAM_RANGE_KEY] if HISTOGRAM_RANGE_KEY in varRunInfo else None)
                
                LOG.info("\tfinished creating figures for: " + explanationName)
            
            # create the report page for this variable
            if (runInfo[DO_MAKE_REPORT_KEY]) :
                
                # hang on to some info on our variable
                variableInspections[displayName] = {
                                                    VARIABLE_RUN_INFO_KEY: varRunInfo
                                                    }
                
                LOG.info ('\tgenerating report for: ' + explanationName) 
                report.generate_and_save_inspect_variable_report(files, varRunInfo, runInfo,
                                                                 variable_stats, spatialInfo, image_names,
                                                                 varRunInfo[VARIABLE_DIRECTORY_KEY], "index.html")
        
        # if we can't do anything with the variable, we should tell the user 
        else :
            message = (explanationName + ' could not be examined. '
                     + 'This may be because the data for this variable (data shape: '
                     + str(aData.shape) + ') does not match the shape of the selected '
                     + 'longitude ' + str(good_shape_from_lon_lat) + ' and '
                     + 'latitude '  + str(good_shape_from_lon_lat) + ' variables.')
            LOG.warn(message)
        
    # the end of the loop to examine all the variables
    
    # generate our general report pages once we've analyzed all the variables
    if (runInfo[DO_MAKE_REPORT_KEY]) :
        
        # get the current time
        runInfo[TIME_INFO_KEY] = datetime.datetime.ctime(datetime.datetime.now())
        
        # TODO, create a new report generation function here
        # make the main summary report
        LOG.info ('generating summary report')
        report.generate_and_save_inspection_summary_report (files,
                                                            pathsTemp[OUT_FILE_KEY], 'index.html',
                                                            runInfo,
                                                            variableInspections,
                                                            spatialInfo,
                                                            nameStats)
        
        # make the glossary
        LOG.info ('generating glossary')
        report.generate_and_save_doc_page(statistics.StatisticalInspectionAnalysis.doc_strings(), pathsTemp[OUT_FILE_KEY])
    
    return 0

def reportGen_library_call (a_path, b_path, var_list=[ ],
                            options_set={ },
                            # todo, this doesn't yet do anything
                            do_document=False,
                            # todo, the output channel does nothing at the moment
                            output_channel=sys.stdout) :
    """
    this method handles the actual work of the reportGen command line tool
    and can also be used as a library routine, pass in the slightly parsed
    command line input, or call it as a library function... be sure to fill
    out the options
    TODO at the moment the options are very brittle and need to be fully filled
    or this method will fail badly (note: the addition of some glance defaults
    has minimized the problem, but you still need to be careful when dealing with
    optional boolean values. this needs more work.)
    """
    
    # have all the variables passed test criteria set for them?
    # if no criteria were set then this will be true
    didPassAll = True
    do_pass_fail = options_set[DO_TEST_PASSFAIL_KEY] # todo, this is a temporary hack, should be loaded with other options
    
    # load the user settings from either the command line or a user defined config file
    pathsTemp, runInfo, defaultValues, requestedNames, usedConfigFile = config_organizer.load_config_or_options(a_path, b_path,
                                                                                                                options_set,
                                                                                                                requestedVars = var_list)
    
    # note some of this information for debugging purposes
    LOG.debug('paths: ' +           str(pathsTemp))
    LOG.debug('defaults: ' +        str(defaultValues))
    LOG.debug('run information: ' + str(runInfo))
    
    # if we wouldn't generate anything, just stop now
    if (not runInfo[DO_MAKE_IMAGES_KEY]) and (not runInfo[DO_MAKE_REPORT_KEY]) :
        LOG.warn("User selection of no image generation and no report generation will result in no " +
                 "content being generated. Aborting generation function.")
        if do_pass_fail :
            return 0 # nothing went wrong, we just had nothing to do!
        else :
            return
    
    # hang onto info to identify who/what/when/where/etc. the report is being run by/for 
    runInfo[MACHINE_INFO_KEY], runInfo[USER_INFO_KEY], runInfo[GLANCE_VERSION_INFO_KEY] = get_run_identification_info()
    
    # deal with the input and output files
    setup_dir_if_needed(pathsTemp[OUT_FILE_KEY], "output")
    # open the files
    files = {}
    LOG.info("Processing File A:")
    aFile = dataobj.FileInfo(pathsTemp[A_FILE_KEY])
    files[A_FILE_TITLE_KEY] = aFile.get_old_info_dictionary() # FUTURE move to actually using the file object to generate the report
    if aFile.file_object is None:
        LOG.warn("Unable to continue with comparison because file a (" + pathsTemp[A_FILE_KEY] + ") could not be opened.")
        sys.exit(1)
    LOG.info("Processing File B:")
    bFile = dataobj.FileInfo(pathsTemp[B_FILE_KEY]) 
    files[B_FILE_TITLE_KEY] = bFile.get_old_info_dictionary() # FUTURE move to actually using the file object to generate the report
    if bFile.file_object is None:
        LOG.warn("Unable to continue with comparison because file b (" + pathsTemp[B_FILE_KEY] + ") could not be opened.")
        sys.exit(1)
    
    # get information about the names the user requested
    finalNames, nameStats = config_organizer.resolve_names(aFile.file_object,
                                                           bFile.file_object,
                                                           defaultValues,
                                                           requestedNames,
                                                           usedConfigFile)
    
    LOG.debug("output dir: " + str(pathsTemp[OUT_FILE_KEY]))
    
    # return for lon_lat_data variables will be in the form 
    #{LON_KEY: longitude_data,      LAT_KEY: latitude_data,      INVALID_MASK_KEY: spaciallyInvalidMaskData}
    # or { } if there is no lon/lat info
    lon_lat_data = { }
    spatialInfo  = { }
    try :
        lon_lat_data, spatialInfo = handle_lon_lat_info (runInfo, aFile, bFile, pathsTemp[OUT_FILE_KEY],
                                                         should_make_images = runInfo[DO_MAKE_IMAGES_KEY],
                                                         fullDPI=runInfo[DETAIL_DPI_KEY], thumbDPI=runInfo[THUMBNAIL_DPI_KEY])
    except ValueError, vle :
        LOG.warn("Error while loading longitude or latitude: ")
        LOG.warn(str(vle))
        exit(1)
    except VariableComparisonError, vce :
        LOG.warn("Error while comparing longitude or latitude: ")
        LOG.warn(str(vce))
        exit(1)
    
    # if there is an approved lon/lat shape, hang on to that for future checks
    good_shape_from_lon_lat = None
    if len(lon_lat_data.keys()) > 0:
        good_shape_from_lon_lat = lon_lat_data[COMMON_KEY][LON_KEY].shape
    
    # this will hold information for the summary report
    # it will be in the form
    # [displayName] =  {
    #                    PASSED_EPSILON_PERCENT_KEY: percent ok with this epsilon,
    #                    FINITE_SIMILAR_PERCENT_KEY: percent with the same finiteness,
    #                    R_SQUARED_COEFF_VALUE_KEY:  the r squared correlation coefficient,
    #                    VARIABLE_RUN_INFO_KEY:      the detailed variable run information
    #                    }
    variableComparisons = {}
    
    # go through each of the possible variables in our files
    # and make a report section with images for whichever ones we can
    for displayName in finalNames:
        
        # pull out the information for this variable analysis run
        varRunInfo = finalNames[displayName].copy()
        
        # get the various names
        technical_name, b_variable_technical_name, \
                explanationName = _get_name_info_for_variable(displayName, varRunInfo)
        
        # make sure that it's possible to load this variable
        if not(aFile.file_object.is_loadable_type(technical_name)) or not(bFile.file_object.is_loadable_type(b_variable_technical_name)) :
            LOG.warn(displayName + " is of a type that cannot be loaded using current file handling libraries included with Glance." +
                    " Skipping " + displayName + ".")
            continue
        
        LOG.info('analyzing: ' + explanationName)
        
        # load the variable data
        aData = load_variable_data(aFile.file_object, technical_name,
                                   dataFilter = varRunInfo[FILTER_FUNCTION_A_KEY] if FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   variableToFilterOn = varRunInfo[VAR_FILTER_NAME_A_KEY] if VAR_FILTER_NAME_A_KEY in varRunInfo else None,
                                   variableBasedFilter = varRunInfo[VAR_FILTER_FUNCTION_A_KEY] if VAR_FILTER_FUNCTION_A_KEY in varRunInfo else None,
                                   altVariableFileObject = dataobj.FileInfo(varRunInfo[VAR_FILTER_ALT_FILE_A_KEY]).file_object if VAR_FILTER_ALT_FILE_A_KEY in varRunInfo else None,
                                   fileDescriptionForDisplay = "file A")
        bData = load_variable_data(bFile.file_object, b_variable_technical_name,
                                   dataFilter = varRunInfo[FILTER_FUNCTION_B_KEY] if FILTER_FUNCTION_B_KEY in varRunInfo else None,
                                   variableToFilterOn = varRunInfo[VAR_FILTER_NAME_B_KEY] if VAR_FILTER_NAME_B_KEY in varRunInfo else None,
                                   variableBasedFilter = varRunInfo[VAR_FILTER_FUNCTION_B_KEY] if VAR_FILTER_FUNCTION_B_KEY in varRunInfo else None,
                                   altVariableFileObject = dataobj.FileInfo(varRunInfo[VAR_FILTER_ALT_FILE_B_KEY]).file_object if VAR_FILTER_ALT_FILE_B_KEY in varRunInfo else None,
                                   fileDescriptionForDisplay = "file B")
        
        # pre-check if this data should be plotted and if it should be compared to the longitude and latitude
        include_images_for_this_variable = ((not(DO_MAKE_IMAGES_KEY in runInfo)) or (runInfo[DO_MAKE_IMAGES_KEY]))
        if DO_MAKE_IMAGES_KEY in varRunInfo :
            include_images_for_this_variable = varRunInfo[DO_MAKE_IMAGES_KEY]
        do_not_test_with_lon_lat = (not include_images_for_this_variable) or (len(lon_lat_data.keys()) <= 0)
        
        # handle vector data
        isVectorData = ( (MAGNITUDE_VAR_NAME_KEY   in varRunInfo) and (DIRECTION_VAR_NAME_KEY   in varRunInfo) and
                         (MAGNITUDE_B_VAR_NAME_KEY in varRunInfo) and (DIRECTION_B_VAR_NAME_KEY in varRunInfo) )
        
        # check if this data can be displayed but
        # don't compare lon/lat sizes if we won't be plotting
        if ( (aData.shape == bData.shape) 
             and 
             ( do_not_test_with_lon_lat
              or
              ((aData.shape == good_shape_from_lon_lat) and (bData.shape == good_shape_from_lon_lat)) ) ) :
            
            # check to see if there is a directory to put information about this variable in,
            # if not then create it
            variableDir = os.path.join(pathsTemp[OUT_FILE_KEY], './' + displayName)
            varRunInfo[VARIABLE_DIRECTORY_KEY] = variableDir
            varRunInfo[VAR_REPORT_PATH_KEY] = quote(os.path.join(displayName, 'index.html'))
            LOG.debug ("Directory selected for variable information: " + varRunInfo[VAR_REPORT_PATH_KEY])
            setup_dir_if_needed(variableDir, "variable")
            
            # form the doc and config paths relative to where the variable is
            upwardPath = './'
            for number in range(len(displayName.split('/'))) : # TODO this is not general to windows
                upwardPath = os.path.join(upwardPath, '../')
            varRunInfo[DOCUMENTATION_PATH_KEY]   = quote(os.path.join(upwardPath, 'doc.html'))
            if CONFIG_FILE_NAME_KEY in runInfo :
                varRunInfo[CONFIG_FILE_PATH_KEY] = quote(os.path.join(upwardPath, runInfo[CONFIG_FILE_NAME_KEY]))
            
            # figure out the masks we want, and then do our statistical analysis
            mask_a_to_use = None if do_not_test_with_lon_lat else lon_lat_data[A_FILE_KEY][INVALID_MASK_KEY]
            mask_b_to_use = None if do_not_test_with_lon_lat else lon_lat_data[B_FILE_KEY][INVALID_MASK_KEY]
            LOG.debug("Analyzing " + displayName + " statistically.")
            variable_stats = statistics.StatisticalAnalysis.withSimpleData(aData, bData,
                                                                           varRunInfo[FILL_VALUE_KEY], varRunInfo[FILL_VALUE_ALT_IN_B_KEY],
                                                                           mask_a_to_use, mask_b_to_use,
                                                                           varRunInfo[EPSILON_KEY], varRunInfo[EPSILON_PERCENT_KEY])
            
            # add a little additional info to our variable run info before we squirrel it away
            varRunInfo[TIME_INFO_KEY] = datetime.datetime.ctime(datetime.datetime.now())  # todo is this needed?
            didPass, epsilon_failed_fraction, \
                     non_finite_fail_fraction, \
                     r_squared_value = variable_stats.check_pass_or_fail(epsilon_failure_tolerance=varRunInfo[EPSILON_FAIL_TOLERANCE_KEY] if EPSILON_FAIL_TOLERANCE_KEY in varRunInfo else numpy.nan,
                                                epsilon_failure_tolerance_default=defaultValues[EPSILON_FAIL_TOLERANCE_KEY],
                                                non_finite_data_tolerance=varRunInfo[NONFINITE_TOLERANCE_KEY]  if NONFINITE_TOLERANCE_KEY in varRunInfo else numpy.nan,
                                                non_finite_data_tolerance_default=defaultValues[NONFINITE_TOLERANCE_KEY],
                                                total_data_failure_tolerance=varRunInfo[TOTAL_FAIL_TOLERANCE_KEY] if TOTAL_FAIL_TOLERANCE_KEY in varRunInfo else numpy.nan,
                                                total_data_failure_tolerance_default=defaultValues[TOTAL_FAIL_TOLERANCE_KEY],
                                                min_acceptable_r_squared=varRunInfo[MIN_OK_R_SQUARED_COEFF_KEY] if MIN_OK_R_SQUARED_COEFF_KEY in varRunInfo else numpy.nan,
                                                min_acceptable_r_squared_default=defaultValues[MIN_OK_R_SQUARED_COEFF_KEY],
                                                )
            
            varRunInfo[DID_VARIABLE_PASS_KEY] = didPass
            # update the overall pass status
            if didPass is not None :
                didPassAll = didPassAll & didPass
            
            # based on the settings and whether the variable passsed or failed,
            # should we include images for this variable?
            if (DO_IMAGES_ONLY_ON_FAIL_KEY in varRunInfo) and varRunInfo[DO_IMAGES_ONLY_ON_FAIL_KEY] :
                include_images_for_this_variable = include_images_for_this_variable and (not didPass)
                varRunInfo[DO_MAKE_IMAGES_KEY] = include_images_for_this_variable
            
            # to hold the names of any images created
            image_names = {
                            ORIGINAL_IMAGES_KEY: [ ],
                            COMPARED_IMAGES_KEY: [ ]
                            }
            
            # create the images for this variable
            if (include_images_for_this_variable) :
                
                plotFunctionGenerationObjects = [ ]
                
                # if there's magnitude and direction data, figure out the u and v, otherwise these will be None
                aUData, aVData = get_UV_info_from_magnitude_direction_info (aFile.file_object,
                                                                            varRunInfo[MAGNITUDE_VAR_NAME_KEY] if (MAGNITUDE_VAR_NAME_KEY) in varRunInfo else None,
                                                                            varRunInfo[DIRECTION_VAR_NAME_KEY] if (DIRECTION_VAR_NAME_KEY) in varRunInfo else None,
                                                                            lon_lat_data[A_FILE_KEY][INVALID_MASK_KEY]
                                                                            if (A_FILE_KEY in lon_lat_data) and (INVALID_MASK_KEY in lon_lat_data[A_FILE_KEY]) else None)
                bUData, bVData = get_UV_info_from_magnitude_direction_info (bFile.file_object,
                                                                            varRunInfo[MAGNITUDE_B_VAR_NAME_KEY] if (MAGNITUDE_B_VAR_NAME_KEY) in varRunInfo else None,
                                                                            varRunInfo[DIRECTION_B_VAR_NAME_KEY] if (DIRECTION_B_VAR_NAME_KEY) in varRunInfo else None,
                                                                            lon_lat_data[B_FILE_KEY][INVALID_MASK_KEY]
                                                                            if (B_FILE_KEY in lon_lat_data) and (INVALID_MASK_KEY in lon_lat_data[B_FILE_KEY]) else None)
                
                # if the data is the same size, we can always make our basic statistical comparison plots
                if (aData.shape == bData.shape) :
                    plotFunctionGenerationObjects.append(plotcreate.BasicComparisonPlotsFunctionFactory())
                
                # if the bin and tuple are defined, try to analyze the data as complex
                # multidimentional information requiring careful sampling
                if (BIN_INDEX_KEY in varRunInfo) and (TUPLE_INDEX_KEY in varRunInfo) :
                    plotFunctionGenerationObjects.append(plotcreate.BinTupleAnalysisFunctionFactory())
                    
                else : # if it's not bin/tuple, there are lots of other posibilities
                    
                    # if it's vector data with longitude and latitude, quiver plot it on the Earth
                    if isVectorData and (not do_not_test_with_lon_lat) :
                        plotFunctionGenerationObjects.append(plotcreate.MappedQuiverPlotFunctionFactory())
                    
                    # if the data is one dimensional we can plot it as lines
                    elif   (len(aData.shape) is 1) : 
                        plotFunctionGenerationObjects.append(plotcreate.LinePlotsFunctionFactory())
                    
                    # if the data is 2D we have some options based on the type of data
                    elif (len(aData.shape) is 2) :
                        
                        # if the data is not mapped to a longitude and latitude, just show it as an image
                        if (do_not_test_with_lon_lat) :
                            plotFunctionGenerationObjects.append(plotcreate.IMShowPlotFunctionFactory())
                        
                        # if it's 2D and mapped to the Earth, contour plot it on the earth
                        else :
                            plotFunctionGenerationObjects.append(plotcreate.MappedContourPlotFunctionFactory())
                
                # plot our lon/lat related info
                image_names[ORIGINAL_IMAGES_KEY], image_names[COMPARED_IMAGES_KEY] = \
                    plot.plot_and_save_comparison_figures \
                            (aData, bData,
                             plotFunctionGenerationObjects,
                             varRunInfo[VARIABLE_DIRECTORY_KEY],
                             displayName,
                             varRunInfo[EPSILON_KEY],
                             varRunInfo[FILL_VALUE_KEY],
                             missingValueAltInB = varRunInfo[FILL_VALUE_ALT_IN_B_KEY] if FILL_VALUE_ALT_IN_B_KEY in varRunInfo else None,
                             lonLatDataDict=lon_lat_data,
                             dataRanges     = varRunInfo[DISPLAY_RANGES_KEY]       if DISPLAY_RANGES_KEY       in varRunInfo else None,
                             dataRangeNames = varRunInfo[DISPLAY_RANGE_NAMES_KEY]  if DISPLAY_RANGE_NAMES_KEY  in varRunInfo else None,
                             dataColors     = varRunInfo[DISPLAY_RANGE_COLORS_KEY] if DISPLAY_RANGE_COLORS_KEY in varRunInfo else None,
                             makeSmall=True,
                             doFork=runInfo[DO_MAKE_FORKS_KEY],
                             shouldClearMemoryWithThreads=runInfo[DO_CLEAR_MEM_THREADED_KEY],
                             shouldUseSharedRangeForOriginal=runInfo[USE_SHARED_ORIG_RANGE_KEY],
                             doPlotSettingsDict = varRunInfo,
                             aUData=aUData, aVData=aVData,
                             bUData=bUData, bVData=bVData,
                             binIndex=      varRunInfo[BIN_INDEX_KEY]       if BIN_INDEX_KEY       in varRunInfo else None,
                             tupleIndex=    varRunInfo[TUPLE_INDEX_KEY]     if TUPLE_INDEX_KEY     in varRunInfo else None,
                             binName=       varRunInfo[BIN_NAME_KEY]        if BIN_NAME_KEY        in varRunInfo else 'bin',
                             tupleName=     varRunInfo[TUPLE_NAME_KEY]      if TUPLE_NAME_KEY      in varRunInfo else 'tuple',
                             epsilonPercent=varRunInfo[EPSILON_PERCENT_KEY] if EPSILON_PERCENT_KEY in varRunInfo else None,
                             fullDPI=       runInfo[DETAIL_DPI_KEY],
                             thumbDPI=      runInfo[THUMBNAIL_DPI_KEY],
                             units_a=       varRunInfo[VAR_UNITS_A_KEY]     if VAR_UNITS_A_KEY     in varRunInfo else None,
                             units_b=       varRunInfo[VAR_UNITS_B_KEY]     if VAR_UNITS_B_KEY     in varRunInfo else None,
                            )#histRange=     varRunInfo[HISTOGRAM_RANGE_KEY] if HISTOGRAM_RANGE_KEY in varRunInfo else None)
                
                LOG.info("\tfinished creating figures for: " + explanationName)
            
            # create the report page for this variable
            if (runInfo[DO_MAKE_REPORT_KEY]) :
                
                # hang on to our good % and other info to describe our comparison
                epsilonPassedPercent = (1.0 -  epsilon_failed_fraction) * 100.0
                finitePassedPercent  = (1.0 - non_finite_fail_fraction) * 100.0 
                variableComparisons[displayName] = {
                                                    PASSED_EPSILON_PERCENT_KEY: epsilonPassedPercent,
                                                    FINITE_SIMILAR_PERCENT_KEY: finitePassedPercent,
                                                    R_SQUARED_COEFF_VALUE_KEY:  r_squared_value,
                                                    VARIABLE_RUN_INFO_KEY:      varRunInfo
                                                    }
                
                LOG.info ('\tgenerating report for: ' + explanationName) 
                report.generate_and_save_variable_report(files,
                                                         varRunInfo, runInfo,
                                                         variable_stats.dictionary_form(),
                                                         spatialInfo,
                                                         image_names,
                                                         varRunInfo[VARIABLE_DIRECTORY_KEY], "index.html")
        
        # if we can't compare the variable, we should tell the user 
        else :
            message = (explanationName + ' ' + 
                     'could not be compared. This may be because the data for this variable does not match in shape ' +
                     'between the two files (file A data shape: ' + str(aData.shape) + '; file B data shape: '
                     + str(bData.shape) + ')')
            if do_not_test_with_lon_lat :
                message = message + '.'
            else :
                message = (message + ' or the data may not match the shape of the selected '
                     + 'longitude ' + str(good_shape_from_lon_lat) + ' and '
                     + 'latitude '  + str(good_shape_from_lon_lat) + ' variables.')
            LOG.warn(message)
        
    # the end of the loop to examine all the variables
    
    # generate our general report pages once we've analyzed all the variables
    if (runInfo[DO_MAKE_REPORT_KEY]) :
        
        # get the current time
        runInfo[TIME_INFO_KEY] = datetime.datetime.ctime(datetime.datetime.now())
        
        # make the main summary report
        LOG.info ('generating summary report')
        report.generate_and_save_summary_report(files,
                                                pathsTemp[OUT_FILE_KEY], 'index.html',
                                                runInfo,
                                                variableComparisons, 
                                                spatialInfo,
                                                nameStats)
        
        # make the glossary
        LOG.info ('generating glossary')
        report.generate_and_save_doc_page(statistics.StatisticalAnalysis.doc_strings(), pathsTemp[OUT_FILE_KEY])
    
    returnCode = 0 if didPassAll else 2 # return 2 only if some of the variables failed
    
    # if we are reporting the pass / fail, return an appropriate status code
    if do_pass_fail :
        LOG.debug("Pass/Fail return code: " + str(returnCode))
        return returnCode

def stats_library_call(afn, bfn, var_list=[ ],
                       options_set={ },
                       do_document=False,
                       output_channel=sys.stdout): 
    """
    this method handles the actual work of the stats command line tool and
    can also be used as a library routine, simply pass in an output channel
    and/or use the returned dictionary of statistics for your own form of
    display.
    TODO, should this move to a different file?
    """
    # unpack some options
    epsilon_val  = options_set[EPSILON_KEY]
    missing_val  = options_set[OPTIONS_FILL_VALUE_KEY]
    do_pass_fail = options_set[DO_TEST_PASSFAIL_KEY]
    
    LOG.debug ("file a: " + afn)
    LOG.debug ("file b: " + bfn)
    
    # open the files
    filesInfo = open_and_process_files([afn, bfn])
    aFile = filesInfo[afn][FILE_OBJECT_KEY]
    bFile = filesInfo[bfn][FILE_OBJECT_KEY]
    
    # information for testing pass/fail if needed
    has_failed = False
    epsilon_fail_tolerance   = 0.0
    nonfinite_fail_tolerance = 0.0
    
    # figure out the variable names and their individual settings
    if len(var_list) <= 0 :
        var_list = ['.*']
    names = config_organizer.parse_varnames( filesInfo[COMMON_VAR_NAMES_KEY], var_list, epsilon_val, missing_val )
    LOG.debug(str(names))
    doc_each  = do_document and len(names)==1
    doc_atend = do_document and len(names)!=1

    for name, epsilon, missing in sorted(names, key=lambda X:X[0]):
        
        # make sure that it's possible to load this variable
        if not(aFile.is_loadable_type(name)) or not(bFile.is_loadable_type(name)) :
            LOG.warn(name + " is of a type that cannot be loaded using current file handling libraries included with Glance." +
                    " Skipping " + name + ".")
            continue
        
        aData = aFile[name]
        bData = bFile[name]
        if missing is None:
            amiss = aFile.missing_value(name)
            bmiss = bFile.missing_value(name)
        else:
            amiss,bmiss = missing,missing
        LOG.debug('comparing %s with epsilon %s and missing %s,%s' % (name,epsilon,amiss,bmiss))
        print >> output_channel, '-'*32
        print >> output_channel, name
        print >> output_channel, ''
        variable_stats = statistics.StatisticalAnalysis.withSimpleData(aData, bData, amiss, bmiss, epsilon=epsilon)
        # if we're doing pass/fail testing, do that now
        if do_pass_fail :
            
            tempDefaults = config_organizer.get_simple_variable_defaults()
            didPass, _, _, _ = variable_stats.check_pass_or_fail(epsilon_failure_tolerance=epsilon_fail_tolerance,
                                                                 epsilon_failure_tolerance_default=tempDefaults[EPSILON_FAIL_TOLERANCE_KEY],
                                                                 non_finite_data_tolerance=nonfinite_fail_tolerance,
                                                                 non_finite_data_tolerance_default=tempDefaults[NONFINITE_TOLERANCE_KEY],
                                                                 total_data_failure_tolerance_default=tempDefaults[TOTAL_FAIL_TOLERANCE_KEY],
                                                                 min_acceptable_r_squared_default=tempDefaults[MIN_OK_R_SQUARED_COEFF_KEY],
                                                                )
            has_failed = has_failed or not(didPass)
        lal = list(variable_stats.dictionary_form().items())
        #lal = list(statistics.summarize(aData, bData, epsilon, (amiss,bmiss)).items()) 
        lal.sort()
        for dictionary_title, dict_data in lal:
            print >> output_channel, '%s' %  dictionary_title
            dict_data
            for each_stat in sorted(list(dict_data)):
                print >> output_channel, '  %s: %s' % (each_stat, dict_data[each_stat])
                if doc_each: print >> output_channel, ('    ' + statistics.StatisticalAnalysis.doc_strings()[each_stat])
            print >> output_channel, '' 
    if doc_atend:
        print >> output_channel, ('\n\n' + statistics.STATISTICS_DOC_STR)
    
    # if we are doing pass/fail, we need to return a status code
    if do_pass_fail :
        status_code = 0
        if has_failed :
            status_code = 3
        LOG.debug("stats is returning status code: " + str(status_code))
        return status_code
    # note: if we aren't doing pass/fail, stats will not return anything

def inspect_stats_library_call (afn, var_list=[ ], options_set={ }, do_document=False, output_channel=sys.stdout): 
    """
    this method handles the actual work of the inspect_stats command line tool and
    can also be used as a library routine, simply pass in an output channel
    and/or use the returned dictionary of statistics for your own form of
    display.
    TODO, should this move to a different file?
    """
    # unpack some options
    missing_val  = options_set[OPTIONS_FILL_VALUE_KEY]
    
    LOG.debug ("file a: " + afn)
    
    # open the file
    filesInfo = open_and_process_files([afn])
    aFile = filesInfo[afn][FILE_OBJECT_KEY]
    
    # figure out the variable names and their individual settings
    if len(var_list) <= 0 :
        var_list = ['.*']
    names = config_organizer.parse_varnames( filesInfo[COMMON_VAR_NAMES_KEY], var_list, epsilon=None, missing=missing_val )
    LOG.debug(str(names))
    doc_each  = do_document and len(names)==1
    doc_atend = do_document and len(names)!=1

    for name, epsilon, missing in sorted(names, key=lambda X:X[0]):

        # make sure that it's possible to load this variable
        if not(aFile.is_loadable_type(name)) :
            LOG.warn(name + " is of a type that cannot be loaded using current file handling libraries included with Glance." +
                    " Skipping " + name + ".")
            continue
        
        aData = aFile[name]
        
        amiss = missing
        if missing is None:
            amiss = aFile.missing_value(name)
        LOG.debug('analyzing %s with missing data value %s' % (name,amiss))
        print >> output_channel, '-'*32
        print >> output_channel, name
        print >> output_channel, ''
        variable_stats = statistics.StatisticalInspectionAnalysis.withSimpleData(aData, amiss)
        lal = list(variable_stats.dictionary_form().items())
        lal.sort()
        for dictionary_title, dict_data in lal:
            print >> output_channel, '%s' %  dictionary_title
            dict_data
            for each_stat in sorted(list(dict_data)):
                print >> output_channel, '  %s: %s' % (each_stat, dict_data[each_stat])
                if doc_each: print >> output_channel, ('    ' + statistics.StatisticalInspectionAnalysis.doc_strings()[each_stat])
            print >> output_channel, '' 
    if doc_atend:
        print >> output_channel, ('\n\n' + statistics.INSP_STATISTICS_DOC_STR)

def gather_stats_for_variable(filehandle, variable):
    missing_val = filehandle.missing_value(variable)
    stats = statistics.StatisticalInspectionAnalysis.withSimpleData(filehandle[variable])
    results = {}
    for title, data in stats.dictionary_form().items():
        results.update(data)
    return results


def return_info_fields(file, input, var, fields):
    """ Return a list of the requested fields from input[var]
    
        fields is itself a list. Values:
        "filename" - value of file
        "variable" - value of var
        "shape" - shape of the variable
        ATTRIBUTE_NAME - Value of this attribute for this variable
        "stats("+NAME+")" - The calculated statistic NAME. Uses same names
            as visible from "glance inspectstats". Only the names are used,
            not the category names.

        Elements in the returned list can be safely passed through str()
        to get a suitable, human-friendly form. No other promises are made.
        Elements may be None if the value is not available.
    """
    result = []
    stats = None
    stats_failed = False
    for f in fields:
        if f == "filename":
            result.append(file)

        elif f == "variable":
            result.append(var)

        elif f == "shape":
            try:
                result.append(str(input[var].shape))
            except ValueError:
                result.append(None)

        elif f.find("stats(") != -1 and f[-1] == ")":
            statname = f[6:-1]
            try:
                if stats is None and stats_failed == False:
                    stats = gather_stats_for_variable(input, var)
            except ValueError:
                LOG.warn('Skipping variable "'+var+'" in "'+file+"' as unparsable.")
                stats_failed = True
                result.append(None)
            if stats is not None and statname in stats:
                result.append(stats[statname])
            else:
                result.append(None)
            
        elif f in input.get_variable_attributes(var):
            result.append(input.get_attribute(var, f))

        else:
            result.append(None)
    return result


def info_impl(options, *args):
    problems = 0

    fields = []
    if options.fields is not None:
        fields = options.fields.split(',')
    fields = ["filename", "variable", "shape"] + fields

    for fn in args:
        try :
            input = io.open(fn)
            lal = list(input())
            lal.sort()
            if options.parsable_output:
                def format_parsable(file, input, var):
                    out_fields = return_info_fields(file, input, var, fields)
                    str_out_fields = [ str(x) if x is not None else "" for x in out_fields ]
                    str_out = "\t".join(str_out_fields)+"\n"
                    return str_out
                print "".join(map(lambda x: format_parsable(fn, input, x), lal))
            else:
                print fn + ': ' + ('\n  ' + ' '*len(fn)).join(lal)
        except KeyError :
            LOG.warn('Unable to open / process file selection: ' + fn)
            problems += 1
    if problems > 255:
        # exit code is 8-bits, limit ourselves.
        problems = 255
    return problems

def main():
    import optparse
    usage = """
%prog [options] 
run "%prog help" to list commands
examples:

glance info A.hdf
glance stats A.hdf B.hdf '.*_prof_retr_.*:1e-4' 'nwp_._index:0'
glance plotDiffs A.hdf B.hdf
glance reportGen A.hdf B.hdf
glance gui
glance inspectStats A.hdf

"""
    
    # set the options available to the user on the command line
    parser = optparse.OptionParser(usage)
    config_organizer.set_up_command_line_options(parser)
    
    # parse the uers options from the command line
    options, args = parser.parse_args()
    if options.self_test:
        import doctest
        doctest.testmod()
        sys.exit(2)
    
    # set up the logging level based on the options the user selected on the command line
    lvl = logging.WARNING
    if options.debug: lvl = logging.DEBUG
    elif options.verbose: lvl = logging.INFO
    elif options.quiet: lvl = logging.ERROR
    logging.basicConfig(level = lvl)
    
    # display the version
    if options.version :
        print (get_glance_version_string() + '\n')

    commands = {}
    prior = None
    prior = dict(locals())
    
    """
    The following functions represent available menu selections in glance.
    """
    
    def info(*args):
        """list information about a list of files
        List available variables for comparison.
        """
        return info_impl(options, *args)
    
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
         glance stats hdffile1 hdffile2
         glance stats --epsilon=0.00001 A.hdf B.hdf baseline_cmask_seviri_cloud_mask:0.002:
         glance -w stats --epsilon=0.00001 A.hdf A.hdf imager_prof_retr_abi_total_precipitable_water_low::-999
        """ 
        afn, bfn = args[:2]
        do_doc = (options.verbose or options.debug)
        
        tempOptions = config_organizer.convert_options_to_dict(options)
        
        # if we were given an output path use that to create the stats
        toPrintTo = sys.stdout
        outpath = clean_path(options.outputpath)
        fileForOutput = None
        if outpath != clean_path('./') :
            
            # if needed, create the directory
            setup_dir_if_needed(outpath, "output")
            
            # open the file for writing, get rid of whatever's there
            fileForOutput = open(outpath + "/stats.txt", "w") # TODO, forming the path this way won't work on windows?
            toPrintTo     = fileForOutput
            
        
        status_result = stats_library_call(clean_path(afn), clean_path(bfn),
                                           var_list=args[2:],
                                           options_set=tempOptions,
                                           do_document=do_doc,
                                           output_channel=toPrintTo)
        
        if fileForOutput is not None :
            fileForOutput.close()
        
        if status_result is not None :
            return status_result

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
         glance plotDiffs A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         glance --outputpath=/path/where/output/will/be/placed/ plotDiffs A.hdf B.hdf
         glance plotDiffs --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
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
         glance reportGen A.hdf B.hdf variable_name_1:epsilon1: variable_name_2 variable_name_3:epsilon3:missing3 variable_name_4::missing4
         glance --outputpath=/path/where/output/will/be/placed/ reportGen A.hdf B.hdf
         glance reportGen --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
         glance reportGen --imagesonly A.hdf B.hdf
        """
        
        tempOptions = config_organizer.convert_options_to_dict(options)
        
        a_path = clean_path(args[0])
        b_path = clean_path(args[1])
        
        return reportGen_library_call(a_path, b_path, args[2:], tempOptions)
    
    def inspectStats(*args):
        """create statistics summary of variables from one file
        Summarize data on variables in a file.
        If no variable names are given, summarize all variables.
        Variable names can be of the form varname::missing to use non-default missing value.
        Variable names can be regular expressions, e.g. 'image.*' or '.*prof_retr.*::-999'
        Missing can be empty to stay with default.
        If _FillValue is an attribute of a variable, that will be used to find missing values where no value is given.
        Run with -v to get more detailed information on the statistics provided.
        Examples:
         glance    inspectStats A.hdf
         glance    inspectStats A.hdf baseline_cmask_seviri_cloud_mask
         glance -w inspectStats A.hdf imager_prof_retr_abi_total_precipitable_water_low::-999
        """ 
        afn = args[0]
        do_doc = (options.verbose or options.debug)
        
        tempOptions = config_organizer.convert_options_to_dict(options)
        
        # TODO, clean up how the output is set up
        # if we were given an output path use that to create the stats
        toPrintTo = sys.stdout
        outpath = clean_path(options.outputpath)
        fileForOutput = None
        if outpath != clean_path('./') :
            
            # if needed, create the directory
            setup_dir_if_needed(outpath, "output")
            
            # open the file for writing, get rid of whatever's there
            fileForOutput = open(outpath + "/stats.txt", "w") # TODO, forming the path this way won't work on windows?
            toPrintTo     = fileForOutput
        
        inspect_stats_library_call(clean_path(afn), var_list=args[1:],
                                   options_set=tempOptions, do_document=do_doc,
                                   output_channel=toPrintTo)
        
        if fileForOutput is not None :
            fileForOutput.close()
    
    def inspectReport(*args) :
        """inspect the contents of a file
        This option creates a report and or images examining variables in a file.
        
        An html report and images detailing the variables in the file will be generated and saved to disk.
        The images will be embedded in the report or visible as separate .png files.
        
        Variables to be compared may be specified after the name of the input file. If no variables
        are specified, all variables that match the shape of the longitude and latitude will be compared.
        Specified variables that do not exist or do not match the lon/lat data shape will be ignored.
        
        The user may also use the notation variable_name::missing_value to specify the missing_value which indicates
        fill data. If this value is absent (in the case of variable_name:: or just variable_name) glance with attempt
        to load the missing value from the file (if none is found, the inspection may fail).
        
        The html report and any created images will be stored in the provided path, or if no path is provided,
        they will be stored in the current directory.
        
        If for some reason you would prefer to generate the report without images, use the --reportonly option. This
        option will generate the html report but omit the images. This may be significantly faster, depending on
        your system, however the information may be more difficult to interpret.
        
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used by default.
        If no longitude or latitude mappings are desired, the --nolonlat option will disable spatial mapping.
        
        Examples:
         glance inspect_report A.hdf variable_name_1:: variable_name_2 variable_name_3::missing3 variable_name_4::missing4
         glance --outputpath=/path/where/output/will/be/placed/ inspect_report A.hdf 
         glance inspect_report --longitude=lon_variable_name --latitude=lat_variable_name A.hdf variable_name
         glance inspect_report --reportonly A.hdf
        """
        
        tempOptions = config_organizer.convert_options_to_dict(options)
        
        # args[0] is the path of the file to be analyzed, an other args should be variable names
        return inspect_library_call(clean_path(args[0]), args[1:], tempOptions)
    
    def colocateData(*args) :
        """colocate data in two files
        
        This option colocates data in the two given input files and saves it to separate output files.
        Data will be colocated based on its corresponding longitude and latitude. Multiple matches may be
        made between a data point in file A and those in file B if they are within the longitude/latitude epsilon.
        Points from each file that could not be matched and the number of duplicate matches will also be
        recorded in the output file.
        
        The user may also use the notation variable_name::missing_value to specify the missing_value which indicates
        missing data. If no missing value is given, glance will attempt to load a missing value from the input file.
        If there is no missing value defined for that variable in the file, no missing value will be analyzed.
        Missing value data points will not be considered for colocation.
        
        Data which corresponds to longitude or latitude values which fall outside the earth (outside the normally
        accepted valid ranges) will also be considered invalid and will not be considered for colocation.
        
        The longitude and latitude variables may be specified with --longitude and --latitude
        If no longitude or latitude are specified the pixel_latitude and pixel_longitude variables will be used.
        The longitude and latitude epsilon may be specified with --llepsilon
        If no longitude/latitude epsilon is given the value of 0.0 (degrees) will be used
        
        The output data files generated by this option will appear in the selected output directory, or the current
        directory if no out put directory is selected. The output files will be named originalFileName-colocation.nc
        (replacing "originalFileName" with the names of your input files).
        
        Examples:
         glance colocateData A.hdf B.hdf variable_name_1 variable_name_2 variable_name_3::missing3 
         glance colocateData --outputpath=/path/where/output/will/be/placed/ A.nc B.nc
         glance colocateData --longitude=lon_variable_name --latitude=lat_variable_name A.hdf B.hdf variable_name
         glance colocateData --llepsilon=0.0001 A.nc B.hdf
        """
        
        # TODO, is this really needed?
        options.imagesOnly = False
        options.htmlOnly   = False
        options.doFork     = False
        
        tempOptions = config_organizer.convert_options_to_dict(options)
        
        # TODO, remove this eventually
        tempOptions[DO_COLOCATION_KEY] = True
        
        a_path = clean_path(args[0])
        b_path = clean_path(args[1])
        
        colocateToFile_library_call(a_path, b_path, args[2:], tempOptions)
    
    # Note: the figure plotting in the GUI is dependant on having selected an interactive renderer in the first "use"
    # statement at the beginning of this module. (It had to be moved into this module to pre-empt other use statempents
    # from imports of other glance modules.)
    def gui (*args) :
        """start the glance graphical user interface
        
        This option launches the graphical user interface for glance. This interface includes only some of the basic
        functionality of glance and may be expanded in the future.
        
        Files to be loaded as File A and File B may be specified on the command line.
        The various output related arguments (quiet, verbose, debug, etc.) may be used if desired.
        
        Examples:
         glance gui
         glance gui A.nc
         glance gui A.nc B.hdf
        """
        
        LOG.debug("Launching Glance GUI")
        temp_controller = gui_control.GlanceGUIController(get_glance_version_string())
        if len(args) >= 1:
            temp_controller.newFileSelected(A_CONST, args[0])
        if len(args) >= 2:
            temp_controller.newFileSelected(B_CONST, args[1])
        temp_controller.launch_gui()
    
    def help(command=None):
        """print help for a specific command or list of commands
        e.g. help stats
        """ # TODO, need to double check that this still works with the lowercase names?

        print_all_summary = False
        if command is None: 
            print_all_summary = True
        else:
            if (command.lower() in lower_locals):
                print lower_locals[command.lower()].__doc__
            else :
                print_all_summary = True

        # print out a list of summaries for each command
        if print_all_summary :
            # print first line of docstring
            for cmd in commands:
                ds = commands[cmd].__doc__.split('\n')[0]
                print "%-16s %s" % (cmd,ds)

    # all the local public functions are considered part of glance, collect them up
    commands.update(dict(x for x in locals().items() if x[0] not in prior))

    # lowercase locals
    # Future: this is an awkward use and could be made more elegant
    lower_locals = { }
    for command_key in commands.keys() :
        lower_locals[command_key.lower()] = locals()[command_key]

    # if what the user asked for is not one of our existing functions, print the help
    if ((not args) or (args[0].lower() not in lower_locals)):
        if options.version:
            return 0;
        parser.print_help()
        help()
        return 9
    else:
        # call the function the user named, given the arguments from the command line, lowercase the request to ignore case
        rc = lower_locals[args[0].lower()](*args[1:])
        return 0 if rc is None else rc
    
    return 0 # it shouldn't be possible to get here any longer

if __name__=='__main__':
    sys.exit(main())
