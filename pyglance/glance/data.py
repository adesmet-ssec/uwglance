#!/usr/bin/env python
# encoding: utf-8
"""
Data objects for use in glance

Created by evas Apr 2010.
Copyright (c) 2010 University of Wisconsin SSEC. All rights reserved.
"""

import logging
import os, subprocess, datetime
import numpy as np

import glance.delta     as delta
import glance.io        as io
import glance.constants as constants

LOG = logging.getLogger(__name__)

class IncompatableDataObjects (ValueError) :
    """
    this exception represents a case where two data objects are completely incompatable
    """
    
    def __init__ (self, aName, bName, dataObjectA=np.nan, dataObjectB=np.nan) :
        """
        create the exception, giving a more specific error message if the objects are passed in
        """
        
        # basic message
        self.message = "Data objects could not be compared."
        
        # if we have the data objects, give a more specific message
        if (dataObjectA is not np.nan) and (dataObjectB is not np.nan) :
            
            # if either object does not exist, they can not be compared
            if (dataObjectA is None) and (dataObjectB is None) :
                self.message = "Both requested data sets were unavailable or did not exist."
                
            # if only one of the two does not exist, give a sligly different message
            elif (dataObjectA is None) or (dataObjectB is None) :
                self.message = ("One of the requested data sets was unavailable or did not exist. " +
                                "A non-existant data set cannot be compared to a data set containing data.")
                
            # check to see if the two variables have the same shape of data
            elif dataObjectA.data.shape != dataObjectB.data.shape :
                self.message = (aName + ' / ' + bName + ' ' +
                                'could not be compared because the data for these variables does not match in shape ' +
                                '(' + aName + ' data shape: ' + str(dataObjectA.data.shape) + '; ' + bName + ' data shape: '
                                + str(dataObjectB.data.shape) + ').')
    
    def __str__(self):
        """
        return our message
        """
        return self.message

class BasicMaskSetObject (object) :
    """
    This class represents a basic set of masks that a data set may have.
    The set must contain an "ignore" mask, and may optionally contain others.
    Note: This item is intended to be read only. If you want to change a mask,
    create a new one with the new masks
    
    ignore_mask - a mask of data that should be ignored for reasons not related to
                  the contents of the actual data set (generally longitude or
                  latitude issues)
    valid_mask - a mask of "good" values (ie. finite and non-missing)
    non_finite_mask - a mask of non-finite values
    missing_mask - a mask of where the data's fill value is present instead of
                   actual data values
    """
    
    def __init__(self, ignoreMask,
                 validMask=None, nonFiniteMask=None, missingMask=None) :
        """
        create the mask set with at least the ignore mask
        (the others are optional)
        """
        self._reset_all_masks()
        
        self.ignore_mask     = ignoreMask
        self.valid_mask      = validMask
        self.non_finite_mask = nonFiniteMask
        self.missing_mask    = missingMask
    
    def _reset_all_masks(self) :
        """
        set all the masks to None
        """
        self.ignore_mask     = None
        self.valid_mask      = None
        self.non_finite_mask = None
        self.missing_mask    = None

class DiffMaskSetObject (BasicMaskSetObject) :
    """
    This class represents a set of masks that related to two or more
    compared data sets. The inherited ignore/valid/non-finite/missing
    masks are used to capture information about where data should be
    ignored/valid/non-finite in the compared data.
    
    Additionally, masks describing mismatch points and points outside
    of the epsilon analysis tolerances are included.
    
    mismatch_mask - a mask of data points which may indicate issues in the data
    outside_epsilon_mask - a mask of points which did not pass the epsilon
                           tolerance testing
    """
    
    def __init__(self, ignoreMask, validInBothMask, mismatchMask, epsilonMask) :
        """
        create a more complex mask, including additional difference information
        """
        self._reset_all_masks()
        
        self.ignore_mask          = ignoreMask
        self.valid_mask           = validInBothMask
        self.mismatch_mask        = mismatchMask
        self.outside_epsilon_mask = epsilonMask

class DataObject (object) :
    """
    This class represents a data set.
    It may include a multidimentional numpy array of data
    as well as the fill value and a set of masks that apply to this data.
    
    data       - the raw array of data (generally this should be a numpy array)
    fill_value - the fill value used in the data array
    masks      - the set of masks that apply to this data
    
    override_fill_value - should the fill_value be used rather than the default_fill_value
                          (this defaults to True so the fill_value is used, insuring backwards compatability)
    default_fill_value  - the default fill value that will be used if override_fill_value is False
    """
    
    def __init__(self, dataArray, fillValue=None, ignoreMask=None,
                 overrideFillValue=True, defaultFillValue=None) :
        """
        Create the data object.
        
        The array of data is expected to be a numpy array.
        The fill value and mask sets are optional.
        If the fill value is provided it is expected to be of the same
        data type as the data array.
        """
        self.data       = dataArray if type(dataArray) == np.ndarray else np.array([dataArray])
        self.fill_value = fillValue
        self.masks      = BasicMaskSetObject(ignoreMask)
        
        self.override_fill_value = overrideFillValue
        self.default_fill_value  = defaultFillValue
        
        self.have_analyzed = False
    
    def copy (self) :
        """
        return a copy of this data object
        """
        
        return DataObject(self.data.copy(), fillValue=self.fill_value, ignoreMask=self.masks.ignore_mask,
                 overrideFillValue=self.override_fill_value, defaultFillValue=self.default_fill_value)

    def holding_array(self):
        """
        Return a version of myself where self.data is always an array.

        Suitable for code paths that insist on an array. 

        If self.data is already an array, returns self.
        If self.data is a simple scalar, copies myself, changing the copy's
        self.data to be an array with a single value, and return the copy.
        """
        if len(self.data.shape) != 0:
            return self
        copy = self.copy()
        copy.data = np.array([self.data.item()])

        ignore_mask = None
        if copy.masks.ignore_mask is not None:
            ignore_mask = np.array([copy.masks.ignore_mask.item()])
        copy.masks      = BasicMaskSetObject(ignore_mask)

        copy.self_analysis(re_do_analysis=True)
        return copy
    
    def self_analysis(self, re_do_analysis=False) :
        """
        Gather some basic information about a data set
        
        Note: If the data has already been analyzed it will not do anything
        unless you send in re_do_analysis=True
        """
        
        # data objects are intended to be immutable, build a new one or override to re-analyze
        if (not self.have_analyzed) or re_do_analysis :
        
            # hang onto the shape for convenience
            shape = self.data.shape
            
            # if there isn't an ignore mask, make an empty one
            if self.masks.ignore_mask is None :
                self.masks.ignore_mask = np.zeros(shape, dtype=np.bool)
            
            # find the non-finite values
            non_finite_mask = ~ (np.isfinite(self.data) | self.masks.ignore_mask)
            #non_finite_mask = np.zeros(shape, dtype=np.bool)
            #np.isfinite(self.data, non_finite_mask)
            #np.logical_or(non_finite_mask, self.masks.ignore_mask, non_finite_mask)
            #np.logical_not(non_finite_mask, non_finite_mask)

            # find and mark the missing values
            missing_mask = np.zeros(shape, dtype=np.bool)
            # if the data has a fill value, mark where the missing data is
            tempFillValue = self.select_fill_value()
            if tempFillValue is not None :
                missing_mask[self.data == tempFillValue] = True
                missing_mask[self.masks.ignore_mask]     = False
            
            # define the valid mask as places where the data is not missing,
            # nonfinite, or ignored
            #valid_mask = ~ (missing_mask | non_finite_mask | self.masks.ignore_mask)
            valid_mask = np.zeros(shape, dtype=np.bool)
            if len(shape) > 0 :
                np.logical_or(missing_mask, non_finite_mask, valid_mask)
                np.logical_or(self.masks.ignore_mask, valid_mask, valid_mask)
                np.logical_not(valid_mask, valid_mask)
            else :
                valid_mask = np.array([ ], dtype=np.bool)
            
            # set our masks
            self.masks = BasicMaskSetObject(self.masks.ignore_mask, valid_mask,
                                            non_finite_mask, missing_mask)
            
            self.have_analyzed = True
    
    def select_fill_value (self) :
        """
        choose the fill value to use
        """
        toReturn = self.fill_value if self.override_fill_value else self.default_fill_value
        
        return toReturn
    
    def get_min (self) :
        """
        get the minimum value in this data set
        """
        
        self.self_analysis()
        return delta.min_with_mask(self.data, self.masks.valid_mask) if len(self.data.shape) > 0 else np.nan
    
    def get_max (self) :
        """
        get the maximum value in this data set
        """
        
        self.self_analysis()
        return delta.max_with_mask(self.data, self.masks.valid_mask) if len(self.data.shape) > 0 else np.nan

    def describe_shape(self):
        """
        describe my data's shape

        Typically just the shape (ex "(50,50)"), but may have
        additional information.  For example, single value shapes
        will also show the value.

        Intended strictly for human viewing, not parsing!
        """
        if self.data.size == 1:
            return str(self.data.shape) + " = " + str(self.data.item())
        return str(self.data.shape)



class DiffInfoObject (object) :
    """
    This class represents the full difference between two data sets.
    
    a_data_object    - data object describing the A data set
    b_data_object    - data object describing the B data set
    diff_data_object - data object describing the raw differences between A and B
    
    epsilon_value    - the epsilon value used for comparison or None
    epsilon_percent  - the percentage (of A) used for epsilon comparisons or None
    (if both a value and percent are present, two epsilon tests will be done)
    """
    
    POSITIVE_UPCASTS = {
                        np.uint8:   np.int16,
                        np.uint16:  np.int32,
                        np.uint32:  np.int64,
                        np.uint64:  np.float32,
                       }
    
    # Upcasts to be used in difference computation to avoid overflow.
    # right now this is agressively upcasting the comparison data
    DATATYPE_UPCASTS = {
                        np.int8:    np.int16,
                        np.int16:   np.int32,
                        np.int32:   np.int64,
                        np.int64:   np.float32,
                        
                        #np.float32: np.float64,
                        #np.float64: np.float128,
                       }
    # FUTURE: right now the actual range of the data isn't being considered when upcasting
    # (Note: numpy.finfo and numpy.iinfo can be used to get more data on types)
    # TODO, replace this with syntax like: np.iinfo(np.uint16).max
    TYPE_MAXIMUM = {
                    np.int16:    32767,
                    np.int32:    2147483647,
                    np.int64:    9223372036854775807,
                    
                    np.float32:  3.4028235e+38,
                    
                    np.float64:  1.7976931348623157e+308,
                    #np.float128: 1.189731495357231765e+4932,
                   }
    
    def __init__(self, aDataObject, bDataObject,
                 epsilonValue=0.0, epsilonPercent=None) :
        """
        analyze the difference between these two data sets at the
        given epsilon values
        """
        
        # set the basic values
        self.a_data_object   = aDataObject
        self.b_data_object   = bDataObject
        self.epsilon_value   = epsilonValue
        self.epsilon_percent = epsilonPercent
        
        # analyze our data and get the difference object
        self.diff_data_object = DiffInfoObject.analyze(aDataObject, bDataObject,
                                                       epsilonValue, epsilonPercent)
    
    @staticmethod
    def _get_shared_type_and_fill_value(data1, data2, fill1=None, fill2=None) :
        """
        Figure out a shared type that can be used when adding or subtracting
        the two data sets given (accounting for possible overflow)
        Also returns a fill value that can be used.
        """
        
        # figure out the shared type
        type_to_return = data1.dtype
        changed_type   = False
        if data1.dtype is not data2.dtype:
            type_to_return = np.common_type(data1, data2)
            changed_type   = True
        
        # make sure we're using a type that has negative values in it
        if type_to_return in DiffInfoObject.POSITIVE_UPCASTS :
            type_to_return = DiffInfoObject.POSITIVE_UPCASTS[type_to_return]
            changed_type = True
        
        # upcast the type if we think we'll need more space for subtracting
        if type_to_return in DiffInfoObject.DATATYPE_UPCASTS :
            type_to_return = DiffInfoObject.DATATYPE_UPCASTS[type_to_return]
            changed_type = True
        
        if changed_type :
            LOG.debug('To prevent overflow, difference data will be upcast from ('
                      + str(data1.dtype) + '/' + str(data2.dtype) + ') to: ' + str(type_to_return))
        
        # figure out the fill value
        fill_value_to_return = None
        
        # if both of the old fill values exist and are the same, use them
        if (fill1 is not None) and (fill1 == fill2) :
            
            fill_value_to_return = fill1
            if changed_type :
                fill_value_to_return = type_to_return(fill_value_to_return)
            
        else: 
            
            # if we're looking at float or complex data, use a nan
            if (np.issubdtype(type_to_return, np.float) or
                np.issubdtype(type_to_return, np.complex)) :
                fill_value_to_return = np.nan
            
            # if we're looking at int data, use the minimum value
            elif np.issubdtype(type_to_return, np.int) :
                fill_value_to_return = np.iinfo(type_to_return).min
            
            # if we're looking at unsigned data, use the maximum value
            elif ((type_to_return is np.uint8)  or
                  (type_to_return is np.uint16) or
                  (type_to_return is np.uint32) or
                  (type_to_return is np.uint64)) :
                fill_value_to_return = np.iinfo(type_to_return).max
        
        return type_to_return, fill_value_to_return
    
    @staticmethod
    def analyze(aDataObject, bDataObject,
                epsilonValue=0.0, epsilonPercent=None):
        """
        analyze the differences between the two data sets
        updates the two data objects with additional masks
        and returns data object containing diff data and masks
        """
        shape = aDataObject.data.shape
        assert(bDataObject.data.shape == shape)
        assert(np.can_cast(aDataObject.data.dtype, bDataObject.data.dtype) or
               np.can_cast(bDataObject.data.dtype, aDataObject.data.dtype))
        
        # do some basic analysis on the individual data sets
        aDataObject.self_analysis()
        bDataObject.self_analysis()
        
        # where is the shared valid data?
        valid_in_both  = aDataObject.masks.valid_mask  & bDataObject.masks.valid_mask
        ignore_in_both = aDataObject.masks.ignore_mask | bDataObject.masks.ignore_mask
        
        # get our shared data type and fill value
        sharedType, fill_data_value = DiffInfoObject._get_shared_type_and_fill_value(aDataObject.data,
                                                                                     bDataObject.data,
                                                                                     aDataObject.select_fill_value(),
                                                                                     bDataObject.select_fill_value())
        
        # we can't continue if we don't have a fill value
        assert(fill_data_value is not None)
        
        # construct our diff'ed data set
        raw_diff = np.zeros(shape, dtype=sharedType)
        raw_diff[~valid_in_both] = fill_data_value # throw away invalid data
        # compute difference, using shared type in computation
        raw_diff[valid_in_both] = bDataObject.data[valid_in_both].astype(sharedType) -  \
                                  aDataObject.data[valid_in_both].astype(sharedType)
        
        # the valid data which is too different between the two sets according to the given epsilon
        outside_epsilon_mask = np.zeros(shape, dtype=np.bool)
        if (epsilonValue   is not None) :
            outside_epsilon_mask |= (abs(raw_diff) > epsilonValue) & valid_in_both
        if (epsilonPercent is not None) :
            outside_epsilon_mask |= (abs(raw_diff) > abs(aDataObject.data * (float(epsilonPercent) / 100.0))) & valid_in_both
        
        # mismatch points = mismatched nans, mismatched missing-values, differences that are too large 
        mismatch_pt_mask = ( (aDataObject.masks.non_finite_mask ^ bDataObject.masks.non_finite_mask) |
                             (aDataObject.masks.missing_mask    ^ bDataObject.masks.missing_mask)    |
                             outside_epsilon_mask )
        
        # make our diff data object
        diff_data_object = DataObject(raw_diff, fillValue=fill_data_value)
        diff_data_object.masks = DiffMaskSetObject(ignore_in_both, valid_in_both,
                                                   mismatch_pt_mask, outside_epsilon_mask)
        
        return diff_data_object
    
    @staticmethod
    def verifyDataCompatability (aDataObject, bDataObject, aName, bName) :
        """
        Confirm that the two data objects can minimally be compared.
        
        raises an IncompatableDataObjects error if the two data objects are not comparable in the most basic of ways
        """
        
        # check the minimum comparison requirements
        if (aDataObject is None) or (bDataObject is None) :
            raise IncompatableDataObjects(aName, bName, dataObjectA=aDataObject, dataObjectB=bDataObject)
        if aDataObject.data.shape != bDataObject.data.shape :
            raise IncompatableDataObjects(aName, bName, dataObjectA=aDataObject, dataObjectB=bDataObject)
        
        return

class FileInfo (object) :
    """
    This class represents information about a file object. It may or may not include the actual file object.
    
    The following member variables are available from this class:
    
    path          - the file path to reach the original file on disk
    md5_sum       - an md5 sum calculated from the original file
    last_modified - the time that the file was last modified (TODO, what form should this be in?)
    file_object   - the file object that can be used to access the data in the file, may be None
    """
    
    def __init__(self, pathToFile, md5sum=None, lastModifiedTime=None, fileObject=None, allowWrite=False) :
        """
        Create the file info object using the values given.
        
        If the md5 sum and last modified time aren't given, the initialization will figure them out.
        Note: if the md5 sum is not given, the file object will also be loaded.
        """
        
        self.path = pathToFile
        
        # if the file doesn't exist, stop
        # TODO, is this the right strategy?
        if not os.path.exists(self.path) :
            LOG.warn("Requested file " + self.path + " could not be opened because it does not exist.")
            self.md5_sum       = None
            self.last_modified = None
            self.file_object   = None
            return
        
        # if the md5 sum isn't given, load the file and figure it out
        if md5sum is None:
            
            # open the file
            LOG.info("Opening " + self.path)
            tempPath       = os.path.abspath(os.path.expanduser(self.path))
            LOG.debug("Provided path after normalization and symbol expansion: " + tempPath)
            fileObject     = io.open(tempPath, allowWrite=allowWrite)
            
            # figure out the md5 sum
            tempSubProcess = subprocess.Popen("md5sum \'" + tempPath + "\'", shell=True, stdout=subprocess.PIPE)
            md5sum         = tempSubProcess.communicate()[0].split()[0]
            LOG.info("File md5sum: " + str(md5sum))
            
        self.md5_sum       = md5sum
        self.file_object   = fileObject
        
        # if the last modified time isn't given, figure it out
        if lastModifiedTime is None :
            
            statsForFile     = os.stat(os.path.abspath(os.path.expanduser(self.path)))
            lastModifiedTime = datetime.datetime.fromtimestamp(statsForFile.st_mtime).ctime() # should time zone be forced?
            LOG.info ("File was last modified: " + lastModifiedTime)
            
        self.last_modified = lastModifiedTime
    
    def get_version_without_file_object (self) :
        """
        get a version of this object without a file object
        (this method is useful if you want file information but do not need access and want to save space)
        """
        toReturn = None
        
        if self.file_object is None:
            toReturn = self
        else:
            toReturn = FileInfo(self.path, self.md5_sum, self.last_modified)
        
        return toReturn
    
    def get_old_info_dictionary (self) :
        """
        get a dictionary of information about this file in the older format
        
        note: this is being used for compatability with the old code and should
        eventually be removed FUTURE
        """
        
        fileInfo = {constants.PATH_KEY: self.path}
        
        if self.md5_sum is not None :
            fileInfo[constants.MD5SUM_KEY] = self.md5_sum
        if self.last_modified is not None:
            fileInfo[constants.LAST_MODIFIED_KEY] = self.last_modified
        
        return fileInfo

if __name__=='__main__':
    import doctest
    doctest.testmod()
