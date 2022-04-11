import os
import numpy
import scipy
import scipy.ndimage
from warnings import warn
import json
from sandbox import set_logger
logger = set_logger(__name__)

class Sensor:
    """
    Wrapping API-class
    """
    def __init__(self, calibsensor: str = None, name: str = 'kinect_v2', crop_values: bool = True,
                 clip_values: bool = True, gauss_filter: bool = True,
                 n_frames: int = 3, gauss_sigma: int = 3, invert: bool = True, **kwargs):
        """
        Sensor Api class to manage the different sensor for the frame adquisition
        Args:
            calibsensor: file path for the .json calibration file of the sensor
            name: type of sensor to use. Current ['kinect_v1', 'kinect_v2', 'lidar', 'dummy']. Predefined is 'kinect_v2'
            crop_values: to crop the frame according to the calibration file
            clip_values: clip the values to the maximum and minimum extent
            gauss_filter: apply a gaussian filter to the data
            n_frames: number of frames to get the average. Avoids anomalies
            gauss_sigma: How strong the filter is
            inverted: The data is measured from the sensor outwards. \
                        This will normalize the data according to the maximun value of the sensor
            **kwargs:
        """
        self.json_filename = calibsensor
        self.version = '2.1.s'
        if calibsensor is None:
            self.s_name = name
            self.s_top = 10
            self.s_right = 10
            self.s_bottom = 10
            self.s_left = 10
            self.s_min = 700
            self.s_max = 1500
            self.s_width = 512
            self.s_height = 424
            self.box_width = 1000
            self.box_height = 800
        else:
            self.load_json(calibsensor)

        if name == 'kinect_v1':
            from .kinectV1 import KinectV1
            try:
                import freenect
                self.Sensor = KinectV1()
            except ImportError:
                logger.warning('Kinect v1 dependencies are not installed', exc_info=True)
                raise ImportError('Kinect v1 dependencies are not installed')
        elif name == 'kinect_v2':
            from .kinectV2 import KinectV2, _platform
            try:
                if _platform == 'Windows':
                    import pykinect2
                elif _platform == 'Linux':
                    import freenect2
                self.Sensor = KinectV2()
            except ImportError:
                logger.warning('Kinect v2 dependencies are not installed', exc_info=True)
                raise ImportError('Kinect v2 dependencies are not installed')
        elif name == 'lidar':
            from .lidar_l515 import LiDAR
            try:
                import pyrealsense2
                self.Sensor = LiDAR()
            except ImportError:
                logger.warning('LiDAR dependencies are not installed', exc_info=True)
                raise ImportError('LiDAR dependencies are not installed')
        elif name == 'D455':
            from .D455 import D455
            try:
                import pyrealsense2
                self.Sensor = D455()
            except ImportError:
                logger.warning('D455 dependencies are not installed', exc_info=True)
                raise ImportError('D455 dependencies are not installed')

        elif name == 'dummy':
            from .dummy import DummySensor
            self.Sensor = DummySensor(extent=self.extent, **kwargs)
        else:
            from .dummy import DummySensor
            logger.warning("Unrecognized sensor name. Activating dummy sensor")
            self.Sensor = DummySensor(extent=self.extent, **kwargs)

        # filter parameters
        self.filter = gauss_filter
        self.n_frames = n_frames
        self.sigma_gauss = gauss_sigma
        self.invert = invert

        self.s_name = self.Sensor.name
        self.s_width = self.Sensor.depth_width
        self.s_height = self.Sensor.depth_height
        self.depth = None
        self.crop = crop_values
        self.clip = clip_values
        self.get_frame()

    def get_raw_frame(self, gauss_filter: bool = True) -> numpy.ndarray:
        """Grab a new height numpy array

        With the Dummy sensor it will sample noise
        """
        # collect last n frames in a stack
        depth_array = self.Sensor.get_frame()
        for i in range(self.n_frames - 1):
            depth_array = numpy.dstack([depth_array, self.Sensor.get_frame()])
        # calculate mean values ignoring zeros by masking them
        depth_array_masked = numpy.ma.masked_where(depth_array == 0, depth_array)  # needed for V2?
        depth = numpy.ma.mean(depth_array_masked, axis=2)
        if gauss_filter:
            # apply gaussian filter
            depth = scipy.ndimage.filters.gaussian_filter(depth, self.sigma_gauss)
        else:
            depth = depth.data

        return depth

    def get_inverted_frame(self, frame):
        """
        Get the current frame and invert the values to get the normalized height,
        being the maximum value of the calibrated sensor data 0.
        Args:
            frame: Sensor frame to invert
        Returns:
            inverted frame
        """
        return self.s_max - frame

    # computed parameters for easy access
    @property
    def s_frame_width(self): return self.s_width - self.s_left - self.s_right

    @property
    def s_frame_height(self): return self.s_height - self.s_top - self.s_bottom

    def load_json(self, file: str):
        """
         Load a calibration file (.JSON format) and actualizes the panel parameters
         Args:
             file: address of the calibration to load

         Returns:

         """

        def json_load(dict_data):
            if dict_data['version'] == self.version:
                self.s_name = dict_data['s_name']
                self.s_top = dict_data['s_top']
                self.s_right = dict_data['s_right']
                self.s_bottom = dict_data['s_bottom']
                self.s_left = dict_data['s_left']
                self.s_min = dict_data['s_min']
                self.s_max = dict_data['s_max']
                self.s_width = dict_data["s_frame_width"] + dict_data['s_right'] + dict_data['s_left']
                self.s_height = dict_data["s_frame_height"] + dict_data['s_top'] + dict_data['s_bottom']
                self.box_width = dict_data['box_width']
                self.box_height = dict_data['box_height']
                logger.info("JSON configuration loaded for sensor.")
            else:
                logger.warning("JSON configuration incompatible."
                               "\nPlease select a valid calibration file or start a new calibration!")

        if os.path.isfile(file):
            with open(file) as calibration_json:
                data = json.load(calibration_json)
                json_load(data)
        else:
            data = json.loads(file)
            json_load(data)
        return True

    def save_json(self, file: str = 'sensor_calibration.json'):
        """
        Saves the current state of the sensor in a .JSON calibration file
        Args:
            file: address to save the calibration

        Returns:

        """
        with open(file, "w") as calibration_json:
            data = {"version": self.version,
                    "s_name": self.s_name,
                    "s_top": self.s_top,
                    "s_right": self.s_right,
                    "s_bottom": self.s_bottom,
                    "s_left": self.s_left,
                    "s_frame_width": self.s_frame_width,
                    "s_frame_height": self.s_frame_height,
                    "s_min": self.s_min,
                    "s_max": self.s_max,
                    "box_width": self.box_width,
                    "box_height": self.box_height}
            json.dump(data, calibration_json)
        logger.info('JSON configuration file saved: %s' % str(file))

    def crop_frame(self, frame: numpy.ndarray) -> numpy.ndarray:
        """ Crops the data frame according to the horizontal margins set up in the calibration
        """

        # TODO: Does not work yet for s_top = 0 and s_right = 0, which currently returns an empty frame!
        # TODO: Workaround: do not allow zeroes in calibration widget and use default value = 1
        # TODO: File numpy issue?
        crop = frame[self.s_bottom:-self.s_top, self.s_left:-self.s_right]
        return crop

    def crop_frame_workaround(self, frame: numpy.ndarray) -> numpy.ndarray:
        # bullet proof working example
        if self.s_top == 0 and self.s_right == 0:
            crop = frame[self.s_bottom:, self.s_left:]
        elif self.s_top == 0:
            crop = frame[self.s_bottom:, self.s_left:-self.s_right]
        elif self.s_right == 0:
            crop = frame[self.s_bottom:-self.s_top, self.s_left:]
        else:
            crop = frame[self.s_bottom:-self.s_top, self.s_left:-self.s_right]
        return crop

    def depth_mask(self, frame: numpy.ndarray) -> numpy.ndarray:
        """ Creates a boolean mask with True for all values within the set sensor range and False for every pixel
        above and below. If you also want to use clipping, make sure to use the mask before.
        """
        # TODO: depth mask is masking everything. returning empty
        mask = numpy.ma.getmask(numpy.ma.masked_outside(frame, self.s_min, self.s_max))
        return mask

    def clip_frame(self, frame: numpy.ndarray) -> numpy.ndarray:
        """ Clips all values outside of the sensor range to the set s_min and s_max values.
        If you want to create a mask make sure to call depth_mask before performing the clip.
        ???"""

        clip = numpy.clip(frame, self.s_min-1, self.s_max+1)
        return clip

    def get_frame(self) -> numpy.ndarray:
        frame = self.get_raw_frame(self.filter)
        if self.Sensor.name == "dummy":
            self.depth = frame
            return self.depth
        if self.crop:
            frame = self.crop_frame(frame)
        if self.clip:
            # frame = self.depth_mask(frame) #TODO: When is this needed?
            frame = self.clip_frame(frame)
        if self.invert:
            frame = self.get_inverted_frame(frame)
        self.depth = frame
        return self.depth

    @property
    def vmax(self):
        """return the maximum extent of the sensor according to the calibration file """
        return numpy.abs(self.s_max - self.s_min)

    @property
    def extent(self):
        """returns the extent in pixels used for the modules to indicate the dimensions of the plot in the sandbox
        [0, width_pixels, 0, height_pixels, 0, distance from maximum point of the sensor to the minimun
        point(total height in mm)] """
        return [0, self.s_frame_width, 0, self.s_frame_height, 0, self.vmax]

    @property
    def physical_dimensions(self):
        """returns the physical extent of the sandbox in mm. Used for scaling gempy models"""
        return [self.box_width, self.box_height]
