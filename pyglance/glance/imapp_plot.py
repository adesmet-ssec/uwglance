#!/usr/bin/env python
# encoding: utf-8
"""
Plot IMAPP IDEA data.

Created by evas Oct 2011.
Copyright (c) 2011 University of Wisconsin SSEC. All rights reserved.
"""

import sys, os, logging

# these first two lines must stay before the pylab import
import matplotlib
matplotlib.use('Agg') # use the Anti-Grain Geometry rendering engine

from pylab import *

import matplotlib.cm     as cm
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from mpl_toolkits.basemap import Basemap

import re
import numpy as np

import glance.data as dataobj

LOG = logging.getLogger(__name__)

defaultValues   = {
                    'longitudeVar':  'xtraj',
                    'latitudeVar':   'ytraj',
                    'initAODVar':    'aod_traj',
                    'trajPressVar':  'ptraj',
                    'timeVar':       'time',
                    'neName':        'TOP_RIGHT_LON_LAT', #TODO is this likely to change?
                    'swName':        'BOTTOM_LEFT_LON_LAT', # TODO is this likely to change?
                    'windLonName':   'Longitude',
                    'windLatName':   'Latitude',
                    'windTimeName':  'time',
                    'windUName':     'uwind',
                    'windVName':     'vwind',
                    'emissNameBase': 'Cloud_Effective_Emissivity_',
                    'aodNameBase':   'Optical_Depth_Land_And_Ocean_',
                    'optLonBase':    'Lon_',
                    'optLatBase':    'Lat_',
                    'figureName':    'frame.png',
                    'figureDPI':     200
                  }

ACCEPTABLE_MAP_PROJECTIONS = ['cylindrical']

LEVELS_FOR_BACKGROUND_PLOTS    = 20
DEFAULT_WINDS_SUBDIVIDE_FACTOR = 1

# a custom colormap or the Trajectory Pressures
color_data = {
    'red'   : ( (0.0,  1.0,  1.0),
                (0.75, 1.0,  1.0),
                (0.9,  1.0,  1.0),
                (1.0,  0.0,  0.0) ),
    'green' : ( (0.0,  1.0,  1.0),
                (0.75, 1.0,  1.0),
                (0.9,  0.08, 0.08),
                (1.0,  0.0,  0.0) ),
    'blue'  : ( (0.0,  1.0,  1.0),
                (0.75, 1.0,  1.0),
                (0.9,  0.58, 0.58),
                (1.0,  0.0,  0.0) )
              }
dark_trajectory_pressure_color_map = matplotlib.colors.LinearSegmentedColormap('darkTrajPressCM', color_data, 256)
color_data = {
    'red'   : ( (0.0,  0.0,  0.0),
                (0.75, 0.0,  0.0),
                (0.9,  1.0,  1.0),
                (1.0,  1.0,  1.0) ),
    'green' : ( (0.0,  0.0,  0.0),
                (0.75, 0.0,  0.0),
                (0.9,  0.08, 0.08),
                (1.0,  1.0,  1.0) ),
    'blue'  : ( (0.0,  0.0,  0.0),
                (0.75, 0.0,  0.0),
                (0.9,  0.58, 0.58),
                (1.0,  1.0,  1.0) )
              }
light_trajectory_pressure_color_map = matplotlib.colors.LinearSegmentedColormap('lightTrajPressCM', color_data, 256)

def _check_requested_projection (projection, doWarn=True, fileDescription="") :
    """
    Check the requested projection, issuing a warning if it is not available and doWarn is true
    """
    
    LOG.debug("Requested map projection: " + str(projection))
    if projection not in ACCEPTABLE_MAP_PROJECTIONS :
        LOG.warn("The requested map projection in " + fileDescription + " (" + str(projection)
                 + ") is not a projection that can be produced by this program. "
                 + "A default projection will be produced. Output may not be displayed as expected.")

def _get_matching_terms_from_list (list_of_strings, regular_expression_text, case_sensitive=False) :
    """
    given a list and a text regular expression in the form taken by the python re module,
    return a list of all strings in the list that match that regular expression
    
    TODO, there's probably a better way to do this, but this is what I've got for now
    """
    
    tempExpression = re.compile(regular_expression_text) if case_sensitive else re.compile(regular_expression_text, re.IGNORECASE)
    
    toReturn = [ ]
    for term in list_of_strings :
        if tempExpression.match(term) is not None :
            toReturn.append(term)
    
    return toReturn

def _find_most_current_index_at_time (times_array, current_time) :
    """
    figure out the index of the data in times_array that is most
    current given that current_time is now
    
    if for some reason the data in the times_array is all after
    current_time, return -1
    otherwise, return the index of the most current data that
    has happened or is happening now (no future indexes!)
    
    note: it is assumed that the times_array is arranged in
    increasing order (earlier to later times) and no time is
    repeated.
    """
    
    toReturn = -1
    
    for indexNum in range(len(times_array)) :
        tempTime = times_array[indexNum]
        if tempTime <= current_time :
            toReturn = indexNum
    
    return toReturn

def _draw_contour_with_basemap (baseMapInstance, data, lonData, latData, levels=None, **kwargs) :
    """
    draw a contour plot of the data using the basemap and the provided lon and lat
    """
    
    # translate into the coordinate system of the basemap
    tempX, tempY = baseMapInstance(lonData, latData)
    
    # show the plot if there is data
    if (data is not None) :
        
        if levels is not None :
            p = baseMapInstance.contourf(tempX, tempY, data, levels, **kwargs)
        else :
            p = baseMapInstance.contourf(tempX, tempY, data, **kwargs)
    
    # TODO, do I need to return tempX and tempY in the future?

def _draw_winds_with_basemap (baseMapInstance,
                              uData,   vData,
                              lonData, latData,
                              valueData=None,
                              **kwargs) :
    """
    draw the given wind vectors using the provided basemap
    
    if the value data isn't None, use it to control the color values plotted on the vectors
    """
    
    # translate into the coordinate system of the basemap
    tempX, tempY = baseMapInstance(lonData, latData)
    
    # show the quiver plot if there is data
    if (uData is not None) and (vData is not None) :
        
        # TODO, it looks like there's a bug that can affect the data sent into quiver, for now copy it
        # bug report can be found here: https://github.com/matplotlib/matplotlib/issues/625
        tempUData = uData.copy()
        tempVData = vData.copy()
        
        kwargs['width'] = 0.001
        kwargs['headwidth'] = 4
        
        if valueData is None:
            p = baseMapInstance.quiver(tempX, tempY, tempUData, tempVData, **kwargs)
        else :
            p = baseMapInstance.quiver(tempX, tempY, tempUData, tempVData, valueData, **kwargs)
    
    # TODO, do I need to return tempX and tempY in the future?

def _plot_pressure_data (baseMapInstance, pressureLat, pressureLon, pressureData=None, colorMap=dark_trajectory_pressure_color_map) :
    """
    plot the pressure data and return the color bar so it can be moved around as needed
    """
    
    colorBarToReturn = None
    
    # if we have pressure data plot that
    if pressureData is not None :
        
        # translate the longitude and latitude into map coordinates
        pressX, pressY =  baseMapInstance(pressureLon, pressureLat)
        
        # I'm taking advantage of the fact that I can remove the black edge line with lw=0 (line width = 0) and scale the marker down with s=0.5
        baseMapInstance.scatter(pressX, pressY, s=3.0, c=pressureData, marker='o', cmap=colorMap, vmin=0, vmax=1000, lw=0)
        
        # create the pressure colorbar
        # TODO, I have no idea why all this BS was necessary to get the colormap in v. 1.1.0 of matplotlib, but not v 1.0.1
        tempMap = cm.ScalarMappable(cmap=colorMap)
        tempMap.set_clim(vmin=0.0, vmax=1000.0)
        tempMap.set_array(pressureData)
        colorBarToReturn = colorbar(tempMap, format='%.5g', orientation='horizontal', shrink=0.25)
        for tempText in colorBarToReturn.ax.get_xticklabels():
            tempText.set_fontsize(5)
        colorBarToReturn.set_label("Trajectory Pressure (mb)")
        
        """ TODO, this is the old version of how I made the pressure color bar that worked fine in v 1.0.1
        colorBarToReturn = colorbar(format='%.5g', orientation='horizontal', shrink=0.25)
        for tempText in colorBarToReturn.ax.get_xticklabels():
            tempText.set_fontsize(5)
        colorBarToReturn.set_label("Trajectory Pressure (mb)")
        """
    
    return colorBarToReturn

def _plot_initial_modis_aod (baseMapInstance, longitude, latitude, initAODdata, colorMap=cm.jet) :
    """
    plot initial modis aod points using the provided base map, return the created
    color bar so it can be moved around as needed
    """
    
    # translate the longitude and latitude into map coordinates
    initX,  initY  = baseMapInstance(longitude,  latitude)
    
    # plot the origin points, these are being scaled to have a thin but visible black border line
    baseMapInstance.scatter(initX,  initY, s=10,  c=initAODdata,  marker='o', cmap=colorMap, vmin=0.0, vmax=1.0, lw=0.5)
    
    # make a color bar
    colorBarToReturn = colorbar(format='%.3g', orientation='horizontal', shrink=0.25)
    for tempText in colorBarToReturn.ax.get_xticklabels():
        tempText.set_fontsize(5)
    colorBarToReturn.set_label("MODIS AOD")
    
    return colorBarToReturn

def _build_basic_figure_with_map (baseMapInstance, parallelWidth=5.0, meridianWidth=5.0, useDarkBackground=True,) :
    """
    create a figure with the longitude and latitude info given
    
    if None is given for the parallelWidth or meridianWidth the parallels or meridians will not be drawn
    """
    
    # create the empty figure
    figure = plt.figure()
    bkgdColor = 'k' if useDarkBackground else 'w' # either use a black or white background
    axes = figure.add_subplot(111, axisbg=bkgdColor)
    
    # draw the basic physical and geopolitical features
    lineColor = 'w' if useDarkBackground else 'k' # either draw black or white lines
    if baseMapInstance is not None :
        baseMapInstance.drawcoastlines( color=lineColor, linewidth=0.5)
        baseMapInstance.drawcountries(  color=lineColor, linewidth=0.5)
        baseMapInstance.drawstates(     color=lineColor, linewidth=0.5)
        baseMapInstance.drawmapboundary(color=lineColor, linewidth=0.5)
    # draw the parallels and meridians
    if parallelWidth is not None :
        parallels = np.arange(-90.,  90., parallelWidth)
        baseMapInstance.drawparallels(parallels,labels=[1,0,0,1], color=lineColor, linewidth=0.5)
    if meridianWidth is not None :
        meridians = np.arange(  0., 360., meridianWidth)
        baseMapInstance.drawmeridians(meridians,labels=[1,0,0,1], color=lineColor, linewidth=0.5)
        # baseMapInstance.drawmeridians([80, 85, 90],labels=[1,0,0,1], color=lineColor, linewidth=0.5)
    
    return axes, figure

# todo, I hate this solution for making contourf show the number of levels that I want,
# but I've searched repeatedly and can't find another way to get it to let me specify
def _make_range_with_data_objects(list_of_data_objects, num_intervals, offset_to_range=0.0) :
    """
    get an array with numbers representing the bounds of a set of ranges
    that covers all the valid data present in the data objects given
    (these may be used for plotting the data)
    if an offset is passed, the outtermost range will be expanded by that much
    
    note: the list of data objects may be 0 or more data objects, if it 0, this
    method returns None since no useful range can be created
    """
    
    if len(list_of_data_objects) <= 0 :
        return None
    
    minVal = np.PINF # positive infinity
    maxVal = np.NINF # negative infinity
    
    # include each data set in the min/max calculations
    for each_data_object in list_of_data_objects :
        minVal = min(each_data_object.get_min(), minVal)
        maxVal = max(each_data_object.get_max(), maxVal)
    
    # TODO, there's the possibility for failure here if all data is fully masked out?
    
    # take any offsets into account
    minVal = minVal - offset_to_range
    maxVal = maxVal + offset_to_range
    
    return np.linspace(minVal, maxVal, num_intervals)

# todo, I hate this solution for making contourf show the number of levels that I want,
# but I've searched repeatedly and can't find another way to get it to let me specify
def _make_range_with_masked_arrays(list_of_masked_arrays, num_intervals, offset_to_range=0.0, optional_top_boundry=None, optional_bottom_boundry=None) :
    """
    get an array with numbers representing the bounds of a set of ranges
    that covers all the valid data present in the masked arrays given
    (these may be used for plotting the data)
    if an offset is passed, the outtermost range will be expanded by that much
    
    If optional top or bottom boundaries are given, the range will be expanded to include them.
    
    note: the list of masked arrays may be 0 or more masked arrays, if it 0, this
    method returns None since no useful range can be created
    """
    
    if len(list_of_masked_arrays) <= 0 :
        return None
    
    minVal = np.PINF # positive infinity
    maxVal = np.NINF # negative infinity
    
    # include each data set in the min/max calculations
    for each_masked_array in list_of_masked_arrays :
        minVal = min(each_masked_array.min(), minVal)
        maxVal = max(each_masked_array.max(), maxVal)
    
    # if we were given optional boundaries, incorporate them
    if optional_top_boundry    is not None:
        maxVal = max(maxVal, optional_top_boundry)
    if optional_bottom_boundry is not None:
        minVal = min(minVal, optional_bottom_boundry)
    
    # TODO, there's the possibility for failure here if all data is fully masked out?
    
    # take any offsets into account
    minVal = minVal - offset_to_range
    maxVal = maxVal + offset_to_range
    
    return np.linspace(minVal, maxVal, num_intervals)

def _create_imapp_figure (initAODdata,       initLongitudeData,       initLatitudeData,
                          pressureData=None, pressLongitudeData=None, pressLatitudeData=None,
                          baseMapInstance=None, figureTitle="MODIS AOD & AOD Trajectories",
                          useDarkBackground=True, parallelWidth=None, meridianWidth=None,
                          windsDataU=None, windsDataV=None, windsDataLon=None, windsDataLat=None,
                          backgroundDataSets={ }) :
    """
    this function is pretty stable now... TODO, documentation forthcoming
    
    backgroundDataSets should be a dictionary in the form
    {
        1: [dataToContourPlot1, LatitudeData1, LongitudeData1, colorMap1, levels],
        2: [dataToContourPlot2, LatitudeData2, LongitudeData2, colorMap2, levels],
        ...
        N: [dataToContourPlotN, LatitudeDataN, LongitudeDataN, colorMapN],
    }
    The keys should all be numbers and the data sets will be plotted in order from lowest key value to highest (allowing z-order control).
    
    """
    
    # create a figure and draw geopolitical features on it
    axes, figure = _build_basic_figure_with_map (baseMapInstance,
                                                 parallelWidth=parallelWidth, meridianWidth=meridianWidth,
                                                 useDarkBackground=useDarkBackground)
    
    # choose the color map
    color_map_to_use = dark_trajectory_pressure_color_map if useDarkBackground else light_trajectory_pressure_color_map
    
    # plot out any background data sets that we have
    for orderKey in sorted(backgroundDataSets.keys()) :
        tempDataSet, tempLatitude, tempLongitude, tempColorMap, tempLevelsList = backgroundDataSets[orderKey]
        _draw_contour_with_basemap (baseMapInstance, tempDataSet, tempLongitude, tempLatitude, cmap=tempColorMap, levels=tempLevelsList, lw=0, antialiased=False)
                                                                                # lw is line width, use 0 to hide the lines between contours
                                                                                # there appears to be a bug in sub-pixel anti-aliasing that is making
                                                                                # contour lines show up even with lw=0, so turn that off for now :(
                                                                                # see also: http://stackoverflow.com/questions/8263769/hide-contour-linestroke-on-pyplot-contourf-to-get-only-fills
    
    # if we have winds to draw, draw those first so they're on the bottom under all the other data
    if ((windsDataU is not None) and (windsDataV is not None) and (windsDataLon is not None) and (windsDataLat is not None)) :
        tempColor = 'w' if useDarkBackground else 'k' # plot our winds in a color that will show up on the background
        _draw_winds_with_basemap (baseMapInstance, windsDataU,   windsDataV, windsDataLon, windsDataLat, color=tempColor)
    
    # plot the pressure data if appropriate
    pressColorBar = _plot_pressure_data(baseMapInstance, pressLatitudeData, pressLongitudeData, pressureData=pressureData, colorMap=color_map_to_use)
    # if we got a color bar back, make sure it's in the right place
    if pressColorBar is not None :
        pressColorBar.ax.set_position([0.4, -0.16, 0.25, 0.25])
    
    # plot the initial modis AOD points after the pressure so the AOD points are always on top (and visible)
    aodColorBar = _plot_initial_modis_aod(baseMapInstance, initLongitudeData, initLatitudeData, initAODdata)
    # if we got a color bar back, make sure it's in the right place
    if aodColorBar is not None :
        aodColorBar.ax.set_position([0.1, -0.16, 0.25, 0.25])
    
    # now that we've moved everything around, make sure our main image is in the right place
    # TODO, make sure this resizing/placement will work in more general cases
    axes.set_position([0.1, 0.15, 0.8, 0.8]) # why was this method so hard to find?
    
    # set up the figure title
    # TODO compose the figure title with time/date info?
    axes.set_title(figureTitle)
    
    return figure

def main():
    import optparse
    usage = """
%prog [options] 
run "%prog help" to list commands
examples:

python -m glance.imapp_plot aodTraj A.nc

"""
    # the following represent options available to the user on the command line:
    
    parser = optparse.OptionParser(usage)
    
    # logging output options
    parser.add_option('-q', '--quiet', dest="quiet",
                    action="store_true", default=False, help="only error output")
    parser.add_option('-v', '--verbose', dest="verbose",
                    action="store_true", default=False, help="enable more informational output")   
    parser.add_option('-w', '--debug', dest="debug",
                    action="store_true", default=False, help="enable debug output")   

    # file generation related options
    parser.add_option('-p', '--outpath', dest="outpath", type='string', default='./',
                    help="set path to output directory")
    
    # display related settings
    parser.add_option('-d', '--windsSubdivideFactor', dest="subdivideFactor", type='int',
                    default=1, help="factor to subdivide and filter out some winds data for visiblity; " +
                                    "higher factors result in fewer winds; data is filtered evenly along the indices of the winds data grid")
    parser.add_option('-m', '--meridianWidth', dest="meridianWidth", type='int',
                      default=5, help="the width in degrees between displayed meridians")
    parser.add_option('-r', '--parallelWidth', dest="parallelWidth", type='int',
                      default=5, help="the width in degrees between displayed parallels")
    
    # time related settings
    parser.add_option('-s', '--startTime', dest="startTime", type='int',
                    default=0, help="set first time to process")
    parser.add_option('-e', '--endTime', dest="endTime", type='int',
                    help="set last time to process")
    parser.add_option('-i', '--timeWindow', dest="timeWindow", type='int',
                    default=6, help="set number of hours of trajectory data to show; 6 hours is the default")
    parser.add_option('-j', '--jumpEmptyStartHours', dest="doJump",
                      action="store_true", help="start generating images on the first hour with trajectory data that is after 0 (ie. not 0); if used this flag " +
                                                "overrrides the start time option when determining which images will be created at the start of a series")
    
    parser.add_option('-t', '--test', dest="self_test",
                action="store_true", default=False, help="run internal unit tests")
    
    # TODO will add this once we're out of alpha
    #parser.add_option('-n', '--version', dest='version',
    #                  action="store_true", default=False, help="view the imapp plot version")
    
    
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
    
    # TODO display the version
    #if options.version :
    #    print (_get_version_string() + '\n')

    commands = {}
    prior = None
    prior = dict(locals())
    
    """
    The following functions represent available menu selections.
    """
    
    def aodTraj(*args):
        """plot AOD trajectory frames
        Given a file with trajectory possitions and pressures over time, plot out
        images of these trajectories on the Earth and save it to disk.
        
        optionally, if a second file with winds data and MODIS cloud effective
        emissivity data is provided, this will also be plotted at comprable time
        steps for each frame
        """
        
        LOG.debug("will startTime be modified by jumping frames? " + str(options.doJump))
        LOG.debug("startTime:  " + str(options.startTime))
        LOG.debug("endTime:    " + str(options.endTime))
        LOG.debug("timeWindow: " + str(options.timeWindow))
        
        # setup the output directory now
        if not (os.path.isdir(options.outpath)) :
            LOG.info("Specified output directory (" + options.outpath + ") does not exist.")
            LOG.info("Creating output directory.")
            os.makedirs(options.outpath)
        
        # open the file
        LOG.info("Opening trajectory data file.")
        trajectoryFilePath = args[0]
        trajectoryFileObject = dataobj.FileInfo(trajectoryFilePath)
        if trajectoryFileObject is None:
            LOG.warn("Trajectory file (" + trajectoryFilePath + ") could not be opened.")
            LOG.warn("Aborting attempt to plot trajectories.")
            sys.exit(1)
        
        # load the required variables
        # TODO, allow the user control over the names?
        LOG.info("Loading variable data from trajectory data file.")
        initialAODdata         = trajectoryFileObject.file_object[defaultValues['initAODVar']]
        trajectoryPressureData = trajectoryFileObject.file_object[defaultValues['trajPressVar']]
        latitudeData           = trajectoryFileObject.file_object[defaultValues['latitudeVar']]
        longitudeData          = trajectoryFileObject.file_object[defaultValues['longitudeVar']]
        trajectoryTimeData     = trajectoryFileObject.file_object[defaultValues['timeVar']]
        
        # get information on where we should display the data
        northeastLon, northeastLat = trajectoryFileObject.file_object.get_global_attribute( defaultValues['neName'] )
        southwestLon, southwestLat = trajectoryFileObject.file_object.get_global_attribute( defaultValues['swName'] )
        LOG.debug ("Viewing window, northeast corner (lat / lon): " + str(northeastLat) + " / " + str(northeastLon))
        LOG.debug ("Viewing window, southwest corner (lat / lon): " + str(southwestLat) + " / " + str(southwestLon))
        parallelWidth = options.parallelWidth
        meridianWidth = options.meridianWidth
        
        # double check the map projection
        _check_requested_projection(trajectoryFileObject.file_object.get_global_attribute("MAP_PROJECTION"), fileDescription="the main trajectory file")
        
        # check to see if we have a second file for the optional data
        LOG.info("Attempting to open optional file (if present)")
        doOptionalWinds, doOptionalCloudEffectiveEmiss, doOptionalDepthLandAndOcean = False, False, False
        optionalDataWindsLatitude, optionalDataWindsLongitude, optionalDataWindsTime, optionalDataWindU, optionalDataWindV = None, None, None, None, None
        listOfCloudEffectiveEmissivityPasses, listOfOpticalDepthLandAndOcean, listOfOptionalLon, listOfOptionalLat = { }, { }, { }, { }
        if len(args) > 1 :
            optionalFilePath = str(args[1])
            LOG.debug("Opening optional file: " + optionalFilePath)
            optionalFileObject = dataobj.FileInfo(optionalFilePath)
            if optionalFileObject is None :
                LOG.warn("Optional file (" + optionalFilePath + ") could not be opened.")
                LOG.warn("Optional winds and cloud effective emissivity data will not be loaded/plotted.")
            else :
                
                # hang on to the list of variables for some checks later
                tempVarList = optionalFileObject.file_object()
                
                # get info on where this data wants to be displayed
                optionalNELon, optionalNELat = optionalFileObject.file_object.get_global_attribute( defaultValues['neName'] )
                optionalSWLon, optionalSWLat = optionalFileObject.file_object.get_global_attribute( defaultValues['swName'] )
                LOG.debug ("Viewing window in optional file, northeast corner (lat / lon): " + str(optionalNELat) + " / " + str(optionalNELon))
                LOG.debug ("Viewing window in optional file, southwest corner (lat / lon): " + str(optionalSWLat) + " / " + str(optionalSWLon))
                
                # if the two viewing windows are not the same, we don't want to display this data TODO, confirm that this is the right strategy?
                if ((optionalNELat != northeastLat) or (optionalNELon != northeastLon) or
                    (optionalSWLat != southwestLat) or (optionalSWLon != southwestLon)) :
                    LOG.debug ("Incompatable viewing area given in optional file. Optional data will not be displayed.")
                    
                else :
                    
                    # double check the map projection
                    _check_requested_projection(optionalFileObject.file_object.get_global_attribute("MAP_PROJECTION"), fileDescription="the optional data file")
                    
                    # otherwise try to get the data we need if possible
                    if ((defaultValues['windLonName']  in tempVarList) and (defaultValues['windLatName'] in tempVarList) and
                        (defaultValues['windTimeName'] in tempVarList) and
                        (defaultValues['windUName']    in tempVarList) and (defaultValues['windVName']   in tempVarList)) :
                        
                        # if we have all the winds related variables available, load the winds data
                        # TODO, should the user be able to control these names?
                        optionalDataWindsLatitude  = optionalFileObject.file_object[defaultValues['windLatName']]
                        optionalDataWindsLongitude = optionalFileObject.file_object[defaultValues['windLonName']]
                        optionalDataWindsTime      = optionalFileObject.file_object[defaultValues['windTimeName']]
                        optionalDataWindU          = optionalFileObject.file_object[defaultValues['windUName']]
                        optionalDataWindV          = optionalFileObject.file_object[defaultValues['windVName']]
                        doOptionalWinds = True
                        
                        # TODO, I'd really rather not do this, for the moment I don't have a choice
                        tempLatSize =  optionalDataWindsLatitude.size
                        tempLonSize = optionalDataWindsLongitude.size
                        tempLat     =  optionalDataWindsLatitude
                        tempLon     = optionalDataWindsLongitude
                        optionalDataWindsLatitude  = np.transpose(np.repeat([tempLat], tempLonSize, axis=0))
                        optionalDataWindsLongitude =              np.repeat([tempLon], tempLatSize, axis=0)
                    
                    # if any cloud effective emissivity swaths are available load them
                    possibleEmissNames = _get_matching_terms_from_list(tempVarList, defaultValues['emissNameBase'])
                    if len(possibleEmissNames) > 0 :
                        LOG.debug("cloud effective emissivity variables found: " + str(possibleEmissNames))
                        for emissName in possibleEmissNames :
                            tempEmissData    = optionalFileObject.file_object[emissName]
                            tempMissingValue = optionalFileObject.file_object.missing_value(emissName)
                            listOfCloudEffectiveEmissivityPasses[emissName] = ma.masked_where(tempEmissData == tempMissingValue, tempEmissData)
                        doOptionalCloudEffectiveEmiss = True
                    
                    # load optical depth land and ocean if it's present
                    possibleOpticalDepthNames = _get_matching_terms_from_list(tempVarList, defaultValues['aodNameBase'])
                    if len(possibleOpticalDepthNames) > 0 :
                        LOG.debug("optical depth land and ocean variables found: " + str(possibleOpticalDepthNames))
                        for aodName in possibleOpticalDepthNames :
                            tempAODData      = optionalFileObject.file_object[aodName]
                            tempMissingValue = optionalFileObject.file_object.missing_value(aodName)
                            listOfOpticalDepthLandAndOcean[aodName] = ma.masked_where(tempAODData == tempMissingValue, tempAODData)
                        doOptionalDepthLandAndOcean = True
                    
                    # if either the cloud effective emissivity or the optical depth land and ocean were loaded,
                    # then we need to load the associated lat and lon variables
                    if doOptionalCloudEffectiveEmiss or doOptionalDepthLandAndOcean :
                        possibleOptionalLatNames = _get_matching_terms_from_list(tempVarList, defaultValues['optLatBase'])
                        possibleOptionalLonNames = _get_matching_terms_from_list(tempVarList, defaultValues['optLonBase'])
                        LOG.debug ("optional longitude variables found: " + str(possibleOptionalLonNames))
                        LOG.debug ("optional latitude  variables found: " + str(possibleOptionalLatNames))
                        # if we can't find lon/lat, we can't plot these! Note: this still fails if we have partial lon/lat, could compare sizes in FUTURE
                        if (len(possibleOptionalLatNames) <= 0) or (len(possibleOptionalLonNames) <= 0) :
                            LOG.warn("Unable to find corresponding longitude and latitude data for some optional variables. "
                                     + "Data without corresponding longitude and latitude data will not be plotted.")
                            doOptionalDepthLandAndOcean   = False
                            doOptionalCloudEffectiveEmiss = False
                        else :
                            # if we found lon and lat, load them
                            for lonName in possibleOptionalLonNames :
                                listOfOptionalLon[lonName] = optionalFileObject.file_object[lonName]
                            for latName in possibleOptionalLatNames :
                                listOfOptionalLat[latName] = optionalFileObject.file_object[latName]
        
        # build a basemap
        LOG.info("Building basemap object.")
        projectionName = 'merc' # use the Mercator Projection; TODO at some point this will need to be checked with a global attribute
        basemapObject  = Basemap (projection=projectionName,llcrnrlat=southwestLat,urcrnrlat=northeastLat,
                                  llcrnrlon=southwestLon, urcrnrlon=northeastLon, lat_ts=20, resolution='l') # TODO do I need to use lat_ts=20, ?
        
        # sort out the times we're using
        timeWindow = options.timeWindow
        startTime    = options.startTime if options.startTime >= 0      else 0
        # if we need to jump to start at the first trajectory data after 0, do that now
        if options.doJump :
            startTimeTemp = trajectoryTimeData[0] if trajectoryTimeData[0] > 0 else trajectoryTimeData[1]
            startTime = int(max(startTime, startTimeTemp))
            # I am assuming that the time data will never be negative
        endTime      = options.endTime   if options.endTime is not None else int(trajectoryTimeData[-1])
        # as a sanity check, it's not really productive to make frames without an end time or for times after our data ends
        if (endTime is None) or (endTime > trajectoryTimeData[-1]) :
            endTime = int(trajectoryTimeData[-1])
        
        # loop over time to create each frame
        initAODFlat =   initialAODdata.ravel()
        initLonData = longitudeData[0].ravel()
        initLatData =  latitudeData[0].ravel()
        for currentTime in range (startTime, endTime + 1) :
            
            # TEMP for debugging during develpment
            LOG.debug ("**********")
            
            # get the time that represents the most current trajectory data
            mostCurrentTrajTimeIndex = _find_most_current_index_at_time (trajectoryTimeData, currentTime)
            # get the time that represents the first point included in the time window
            firstTimeIncludedIndex    = _find_most_current_index_at_time (trajectoryTimeData, (currentTime - timeWindow))
            
            # only get data to plot the trajectory points if there is some available
            thisFramePressures = None
            thisFramePressLon  = None
            thisFramePressLat  = None
            if mostCurrentTrajTimeIndex >= firstTimeIncludedIndex :
                
                # TODO , double check that this isn't off by one
                LOG.debug("Most current time index: " + str(mostCurrentTrajTimeIndex))
                LOG.debug("First time window index: " + str(firstTimeIncludedIndex))
                LOG.debug("Most current time time:  " + str(trajectoryTimeData[mostCurrentTrajTimeIndex]))
                LOG.debug("First time window time:  " + str(trajectoryTimeData[firstTimeIncludedIndex]))
                
                # now pull out the pressure data and related lon/lat info for plotting
                thisFramePressures = trajectoryPressureData[firstTimeIncludedIndex : mostCurrentTrajTimeIndex+1].ravel()
                thisFramePressLon  =          longitudeData[firstTimeIncludedIndex : mostCurrentTrajTimeIndex+1].ravel()
                thisFramePressLat  =           latitudeData[firstTimeIncludedIndex : mostCurrentTrajTimeIndex+1].ravel()
            
            # we need to plot the winds under the other data so they don't cover it up
            currentWindsU, currentWindsV, currentWindsLon, currentWindsLat = None, None, None, None
            if doOptionalWinds :
                # figure out which winds data we should use
                mostCurrentWindsTimeIndex = _find_most_current_index_at_time (optionalDataWindsTime, currentTime)
                LOG.debug("Optional winds most current time index: " + str(mostCurrentWindsTimeIndex))
                LOG.debug("Time of most recent optional winds:     " + str(optionalDataWindsTime[mostCurrentWindsTimeIndex]))
                # check to make sure we found any winds at the current time
                if mostCurrentWindsTimeIndex > -1 :
                    currentWindsU             =          optionalDataWindU[mostCurrentWindsTimeIndex]
                    currentWindsV             =          optionalDataWindV[mostCurrentWindsTimeIndex]
                    
                    maskingFactor = options.subdivideFactor if options.subdivideFactor > 0 else DEFAULT_WINDS_SUBDIVIDE_FACTOR
                    LOG.debug ("Using winds subdivide factor: " + str(maskingFactor))
                    maskTemp = np.zeros(currentWindsV.shape, dtype=np.bool)
                    if maskingFactor > 1 :
                        maskTemp1 = np.ones(currentWindsV.shape, dtype=np.bool)
                        maskTemp2 = np.ones(currentWindsV.shape, dtype=np.bool)
                        numbers1  =              np.repeat([range(currentWindsV.shape[1])], currentWindsV.shape[0], axis=0)
                        numbers2  = np.transpose(np.repeat([range(currentWindsV.shape[0])], currentWindsV.shape[1], axis=0))
                        maskTemp1 [ numbers1 % maskingFactor == 0 ] = False
                        maskTemp2 [ numbers2 % maskingFactor == 0 ] = False
                        maskTemp  = maskTemp1 | maskTemp2
                    currentWindsU = np.ma.array(currentWindsU, mask=maskTemp)
                    currentWindsV = np.ma.array(currentWindsV, mask=maskTemp)
            
            # build up the background data sets we want to plot
            backgroundData = { }
            zCounter = 1
            
            # if we're doing cloud effective emissivity, add those to the background list
            if doOptionalCloudEffectiveEmiss :
                tempLevels = _make_range_with_masked_arrays(listOfCloudEffectiveEmissivityPasses.values(), LEVELS_FOR_BACKGROUND_PLOTS,
                                                            optional_bottom_boundry=0.0, optional_top_boundry=1.0)
                for emissName in sorted(listOfCloudEffectiveEmissivityPasses.keys()) :
                    emissSetNumber = emissName.split('_')[-1] # get the number off the end of the name
                    # if the numbering is at all different between the variables, this will fail
                    backgroundData[zCounter] = [listOfCloudEffectiveEmissivityPasses[emissName],
                                                    listOfOptionalLat[defaultValues['optLatBase'] + emissSetNumber],
                                                    listOfOptionalLon[defaultValues['optLonBase'] + emissSetNumber],
                                                    matplotlib.cm.gray, tempLevels]
                    zCounter = zCounter + 1
            
            # if we're doing the optical depth land and ocean, add those to the background list too
            if doOptionalDepthLandAndOcean :
                tempLevels = _make_range_with_masked_arrays(listOfOpticalDepthLandAndOcean.values(), LEVELS_FOR_BACKGROUND_PLOTS,
                                                            optional_bottom_boundry=0.0, optional_top_boundry=1.0)
                for aodName in sorted(listOfOpticalDepthLandAndOcean.keys()) :
                    aodNumber = aodName.split('_')[-1] # get the number off the end of the name
                    # if the numbering is at all different between the variables, this will fail
                    backgroundData[zCounter] = [listOfOpticalDepthLandAndOcean[aodName],
                                                    listOfOptionalLat[defaultValues['optLatBase'] + aodNumber],
                                                    listOfOptionalLon[defaultValues['optLonBase'] + aodNumber],
                                                    matplotlib.cm.jet, tempLevels]
                    zCounter = zCounter + 1
            
            # make the plot
            LOG.info("Creating trajectory plot for time " + str(float(currentTime)) + ".")
            tempFigure = _create_imapp_figure (initAODFlat,                     initLonData,                          initLatData,
                                               pressureData=thisFramePressures, pressLongitudeData=thisFramePressLon, pressLatitudeData=thisFramePressLat,
                                               baseMapInstance=basemapObject, parallelWidth=parallelWidth, meridianWidth=meridianWidth,
                                               windsDataU=currentWindsU, windsDataV=currentWindsV,
                                               windsDataLon=optionalDataWindsLongitude, windsDataLat=optionalDataWindsLatitude,
                                               figureTitle="MODIS AOD & AOD Trajectories on " + str(currentTime) + "Z",
                                               backgroundDataSets=backgroundData)
                                               # TODO, the figure title needs to have the dates in it and the day may roll over, so current time can't be put in directly
            
            # save the plot to disk
            LOG.info("Saving plot to disk.")
            tempFigure.savefig(os.path.join(options.outpath, str(currentTime) + defaultValues['figureName']), dpi=defaultValues['figureDPI'])
            
            # get rid of the figure 
            plt.close(tempFigure)
            del(tempFigure)
    
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
    
    # all the local public functions are considered part of this program, collect them up
    commands.update(dict(x for x in locals().items() if x[0] not in prior))    
    
    # if what the user asked for is not one of our existing functions, print the help
    if (not args) or (args[0] not in commands): 
        parser.print_help()
        help()
        return 9
    else:
        # call the function the user named, given the arguments from the command line  
        locals()[args[0]](*args[1:])

    return 0


if __name__=='__main__':
    sys.exit(main())