# This file is part of hvsrpy, a Python package for horizontal-to-vertical
# spectral ratio processing.
# Copyright (C) 2019-2020 Joseph P. Vantassel (jvantassel@utexas.edu)
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https: //www.gnu.org/licenses/>.

"""Class definition for Sensor3c, a 3-component sensor."""

import math
import logging
import json
import pandas as pd
import mmap

import numpy as np
import obspy
from sigpropy import TimeSeries, FourierTransform, WindowedTimeSeries, FourierTransformSuite

from hvsrpy import Hvsr, HvsrRotated

logger = logging.getLogger(__name__)

__all__ = ["Sensor3c"]


class Sensor3c():
    """Class for creating and manipulating 3-component sensor objects.

    Attributes
    ----------
    ns : TimeSeries
        North-south component, time domain.
    ew : TimeSeries
        East-west component, time domain.
    vt : TimeSeries
        Vertical component, time domain.

    """

    @staticmethod
    def _check_input(values_dict):
        """Perform checks on inputs.

        Specifically:
            1. Ensure all components are `TimeSeries` objects.
            2. Ensure all components have equal `dt`.
            3. Ensure all components have same `nsamples`. If not trim
            components to the common length.

        Parameters
        ----------
        values_dict : dict
            Key is human readable component name {'ns', 'ew', 'vt'}.
            Value is corresponding `TimeSeries` object.

        Returns
        -------
        Tuple
            Containing checked components.

        """
        ns = values_dict["ns"]
        if not isinstance(ns, TimeSeries):
            msg = f"'ns' must be a `TimeSeries`, not {type(ns)}."
            raise TypeError(msg)
        dt = ns.dt
        nsamples = ns.nsamples
        flag_cut = False
        for key, value in values_dict.items():
            if key == "ns":
                continue
            if not isinstance(value, TimeSeries):
                msg = f"`{key}`` must be a `TimeSeries`, not {type(value)}."
                raise TypeError(msg)
            if value.dt != dt:
                msg = f"All components must have equal `dt`."
                raise ValueError(msg)
            if value.nsamples != nsamples:
                logging.info("Components are not of the same length.")
                flag_cut = True

        if flag_cut:
            min_time = 0
            max_time = np.inf
            for value in values_dict.values():
                min_time = max(min_time, min(value.time))
                max_time = min(max_time, max(value.time))
            logging.info(f"Trimming between {min_time} and {max_time}.")
            for value in values_dict.values():
                value.trim(min_time, max_time)

        return (values_dict["ns"], values_dict["ew"], values_dict["vt"])

    def __init__(self, ns, ew, vt, meta=None):
        """Initialize a 3-component sensor (Sensor3c) object.

        Parameters
        ----------
        ns, ew, vt : TimeSeries
            `TimeSeries` object for each component.
        meta : dict, optional
            Meta information for object, default is None.

        Returns
        -------
        Sensor3c
            Initialized 3-component sensor object.

        """
        self.ns, self.ew, self.vt = self._check_input({"ns": ns,
                                                       "ew": ew,
                                                       "vt": vt})
        self.meta = meta

    @property
    def normalization_factor(self):
        """Time history normalization factor across all components."""
        factor = 1E-6
        for attr in ["ns", "ew", "vt"]:
            cmax = np.max(np.abs(getattr(self, attr).amp.flatten()))
            factor = cmax if cmax > factor else factor
        return factor

    @classmethod
    def from_mseed(cls, fname):
        """Initialize a 3-component sensor (Sensor3c) object from a
        .miniseed file.

        Parameters
        ----------
        fname : str
            Name of miniseed file, full path may be used if desired.
            The file should contain three traces with the
            appropriate channel names. Refer to the `SEED` Manual
            `here <https://www.fdsn.org/seed_manual/SEEDManual_V2.4.pdf>`_.
            for specifics.

        Returns
        -------
        Sensor3c
            Initialized 3-component sensor object.

        """
        traces = obspy.read(fname)

        if len(traces) != 3:
            msg = f"miniseed file {fname} has {len(traces)} traces, but should have 3."
            raise ValueError(msg)

        found_ew, found_ns, found_vt = False, False, False
        for trace in traces:
            if trace.meta.channel.endswith("E") and not found_ew:
                ew = TimeSeries.from_trace(trace)
                found_ew = True
            elif trace.meta.channel.endswith("N") and not found_ns:
                ns = TimeSeries.from_trace(trace)
                found_ns = True
            elif trace.meta.channel.endswith("Z") and not found_vt:
                vt = TimeSeries.from_trace(trace)
                found_vt = True
            else:
                msg = f"Missing, duplicate, or incorrectly named components. See documentation."
                raise ValueError(msg)

        meta = {"File Name": fname}
        return cls(ns, ew, vt, meta)

    def to_dict(self):
        """Dictionary representation of `Sensor3c` object.

        Returns
        -------
        dict
            With all of the components of the `Sensor3c`.

        """
        dictionary = {}
        for name in ["ns", "ew", "vt", "meta"]:
            value = getattr(self, name)
            if name != "meta":
                value = value.to_dict()
            dictionary[name] = value
        return dictionary

    @classmethod
    def from_dict(cls, dictionary):
        """Create `Sensor3c` object from dictionary representation.

        Parameters
        ---------
        dictionary : dict
            Must contain keys "ns", "ew", and "vt", and may also contain
            the optional key "meta". "ns", "ew", and "vt" must be
            dictionary representations of `TimeSeries` objects, see
            `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
            documentation for details.

        Returns
        -------
        Sensor3c
            Instantiated `Sensor3c` object.

        """
        if dictionary.get("meta") is None:
            dictionary["meta"] = None

        comps = []
        for comp in ["ns", "ew", "vt"]:
            comps.append(TimeSeries.from_dict(dictionary[comp]))

        return cls(*comps, dictionary["meta"])

    def to_json(self):
        """Json string representation of `Sensor3c` object.

        Returns
        -------
        str
            With all of the components of the `Sensor3c`.

        """
        dictionary = self.to_dict()
        return json.dumps(dictionary)

    @classmethod
    def from_json(cls, json_str):
        """Create `Sensor3c` object from Json-string representation.

        Parameters
        ---------
        json_str : str
            Json-style string, which must contain keys "ns", "ew", and
            "vt", and may also contain the optional key "meta". "ns",
            "ew", and "vt" must be Json-style string representations of
            `TimeSeries` objects, see
            `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
            documentation for details.

        Returns
        -------
        Sensor3c
            Instantiated `Sensor3c` object.

        """
        dictionary = json.loads(json_str)
        return cls.from_dict(dictionary)

    @classmethod
    def from_saf(cls, fname):
        """Create `Sensor3c` object from a SAF ASCII file.

        Parameters
        ---------
        fname : str
            Name of the SESAME ASCII (SAF) file.

        Returns
        -------
        Sensor3c
            Instantiated `Sensor3c` object.

        """

        meta = {}
        meta["File Name"] = fname

        with open(fname) as fsaf:
            # Look for some parameters in the header and
            # for the line where data start.
            for num, line in enumerate(fsaf, 1):
                spl = line.split()
                if "####----" in line:
                    # Data should start from here
                    data_start = num
                    break
                if spl:
                    # List is not empty
                    if spl[0] == "SAMP_FREQ":
                        # Collect the sampling frequency
                        # CHECK HERE IF THE SAMPLING FREQUENCY IS OK!
                        samp_freq = float(spl[2])
                    elif spl[0] == "PROJECT_NAME":
                        try:
                            # Collect the name of the project
                            project_name = spl[2]
                        except IndexError:
                            # No name provided for the project
                            project_name = None
                        meta["project_name"] = project_name
                    elif spl[0] == "START_TIME":
                        starttime = obspy.UTCDateTime(int(spl[2]),
                                                      int(spl[3]),
                                                      int(spl[4]),
                                                      int(spl[5]),
                                                      int(spl[6]),
                                                      int(spl[7]))
                        meta["starttime"] = spl[2]+"/"+spl[3]+"/"+spl[4]+" "+spl[5]+":"+spl[6]+":"+spl[7]
                    elif spl[0] == "EVT_X":
                        meta["evt_x"] = spl[2]
                    elif spl[0] == "EVT_Y":
                        meta["evt_y"] = spl[2]
                    elif spl[0] == "EVT_Z":
                        meta["evt_z"] = spl[2]
                        
                                                      

                        
        # Read the dataset unsing pandas 
        data = pd.read_csv(fname, sep=r"\s+", skiprows=data_start, header=None, float_precision="round_trip")
        data.rename(columns={0: "vt",1: "ns", 2:"ew"}, inplace=True)

        trace_ew = obspy.Trace()
        trace_ew.data = data["ew"].to_numpy()
        trace_ew.stats.sampling_rate = samp_freq
        trace_ew.stats.starttime = starttime        
        
        ew = TimeSeries.from_trace(trace_ew)
        
        trace_ns = obspy.Trace()
        trace_ns.data = data["ns"].to_numpy()
        trace_ns.stats.sampling_rate = samp_freq
        trace_ns.stats.starttime = starttime                
        ns = TimeSeries.from_trace(trace_ns)
        
        trace_vt = obspy.Trace()
        trace_vt.data = data["vt"].to_numpy()
        trace_vt.stats.sampling_rate = samp_freq
        trace_vt.stats.starttime = starttime                        
        vt = TimeSeries.from_trace(trace_vt)


        
        return cls(ns, ew, vt, meta)    

    def split(self, windowlength):
        """Split component `TimeSeries` into `WindowedTimeSeries`.

        Refer to `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
        documentation for details.

        """
        for attr in ["ew", "ns", "vt"]:
            wtseries = WindowedTimeSeries.from_timeseries(getattr(self, attr),
                                                          windowlength)
            setattr(self, attr, wtseries)

    def detrend(self):
        """Detrend components.

        Refer to `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
        documentation for details.

        """
        for comp in [self.ew, self.ns, self.vt]:
            comp.detrend()

    def bandpassfilter(self, flow, fhigh, order):  # pragma: no cover
        """Bandpassfilter components.

        Refer to `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
        documentation for details.

        """
        for comp in [self.ew, self.ns, self.vt]:
            comp.bandpassfilter(flow, fhigh, order)

    def cosine_taper(self, width):
        """Cosine taper components.

        Refer to `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_
        documentation for details.

        """
        for comp in [self.ew, self.ns, self.vt]:
            comp.cosine_taper(width)

    def transform(self, **kwargs):
        """Perform Fourier transform on components.

        Returns
        -------
        dict
            With `FourierTransform`-like objects, one for for each
            component, indicated by the key 'ew','ns', 'vt'.

        """
        ffts = {}
        for attr in ["ew", "ns", "vt"]:
            tseries = getattr(self, attr)
            if isinstance(tseries, WindowedTimeSeries):
                fft = FourierTransformSuite.from_timeseries(tseries, **kwargs)
            elif isinstance(tseries, TimeSeries):
                fft = FourierTransform.from_timeseries(tseries, **kwargs)
            else:
                raise NotImplementedError
            ffts[attr] = fft
        return ffts

    def combine_horizontals(self, method, horizontals, azimuth=None):
        """Combine two horizontal components (`ns` and `ew`).

        Parameters
        ----------
        method : {'squared-average', 'geometric-mean', 'azimuth'}
            Defines how the two horizontal components are combined
            to represent a single horizontal component.
        horizontals : dict
            If combination is done in the frequency-domain (i.e.,
            `method in ['squared-average', 'geometric-mean']`)
            horizontals is a `dict` of `FourierTransform` objects,
            see meth: tranform for details. If combination is done in
            the time-domain (i.e., `method in ['azimuth']`)
            horizontals is a `dict` of `TimeSeries` objects.
        azimuth : float, optional
            Valid only if `method` is `azimuth` in which case an azimuth
            (clockwise positive) from North (i.e., 0 degrees) is
            required.

        Returns
        -------
        FourierTransform or TimeSeries
            Depending upon whether method is performed in the
            frequency-domain or time-domain, respectively.

        """
        if method in ["squared-average", "geometric-mean"]:
            return self._combine_horizontal_fd(method, horizontals)
        elif method == 'azimuth':
            return self._combine_horizontal_td(method, horizontals, azimuth=azimuth)
        else:
            msg = f"`method`={method} has not been implemented."
            raise NotImplementedError(msg)

    @staticmethod
    def _combine_horizontal_fd(method, horizontals, **kwargs):
        ns = horizontals["ns"]
        ew = horizontals["ew"]

        if method == 'squared-average':
            horizontal = np.sqrt((ns.mag*ns.mag + ew.mag*ew.mag)/2)
        elif method == 'geometric-mean':
            horizontal = np.sqrt(ns.mag * ew.mag)
        else:
            msg = f"`method`={method} has not been implemented."
            raise NotImplementedError(msg)

        if isinstance(ns, FourierTransformSuite):
            return FourierTransformSuite(horizontal, ns.frq)
        elif isinstance(ns, FourierTransform):
            return FourierTransform(horizontal, ns.frq)
        else:
            raise NotImplementedError

    def _combine_horizontal_td(self, method, horizontals, azimuth):
        az_rad = math.radians(azimuth)
        ns = horizontals["ns"]
        ew = horizontals["ew"]

        if method == 'azimuth':
            horizontal = ns.amp*math.cos(az_rad) + ew.amp*math.sin(az_rad)
        else:
            msg = f"method={method} has not been implemented."
            raise NotImplementedError(msg)

        if isinstance(ns, WindowedTimeSeries):
            return WindowedTimeSeries(horizontal, ns.dt)
        elif isinstance(ns, TimeSeries):
            return TimeSeries(horizontal, ns.dt)
        else:
            raise NotImplementedError

    def hv(self, windowlength, bp_filter, taper_width, bandwidth,
           resampling, method, azimuth=None):
        """Prepare time series and Fourier transforms then compute H/V.

        More information for the all parameters can be found in
        the documentation of
        `SigProPy <https://sigpropy.readthedocs.io/en/latest/?badge=latest>`_.

        Parameters
        ----------
        windowlength : float
            Length of time windows in seconds.
        bp_filter : dict
            Bandpass filter settings, of the form
            {'flag':`bool`, 'flow':`float`, 'fhigh':`float`,
            'order':`int`}.
        taper_width : float
            Width of cosine taper.
        bandwidth : float
            Bandwidth of the Konno and Ohmachi smoothing window.
        resampling : dict
            Resampling settings, of the form
            {'minf':`float`, 'maxf':`float`, 'nf':`int`,
            'res_type':`str`}.
        method : {'squared-averge', 'geometric-mean', 'azimuth'}
            Refer to :meth:`combine_horizontals <Sensor3c.combine_horizontals>`
            for details.
        azimuth : float, optional
            Refer to :meth:`combine_horizontals <Sensor3c.combine_horizontals>`
            for details.

        Returns
        -------
        Hvsr
            Instantiated `Hvsr` object.

        """
        if bp_filter["flag"]:
            self.bandpassfilter(flow=bp_filter["flow"],
                                fhigh=bp_filter["fhigh"],
                                order=bp_filter["order"])
        self.split(windowlength)
        self.detrend()
        self.cosine_taper(width=taper_width)

        if method in ["squared-average", "geometric-mean", "azimuth"]:
            return self._make_hvsr(method=method,
                                   resampling=resampling,
                                   bandwidth=bandwidth,
                                   azimuth=azimuth)
        elif method in ["rotate"]:
            hvsrs = np.empty(len(azimuth), dtype=object)
            for index, az in enumerate(azimuth):
                hvsrs[index] = self._make_hvsr(method="azimuth",
                                               resampling=resampling,
                                               bandwidth=bandwidth,
                                               azimuth=az)
            return HvsrRotated.from_iter(hvsrs, azimuth)
        else:
            msg = f"`method`={method} has not been implemented."
            raise NotImplementedError(msg)

    def _make_hvsr(self, method, resampling, bandwidth, azimuth=None):
        if method in ["squared-average", "geometric-mean"]:
            ffts = self.transform()
            hor = self.combine_horizontals(method=method, horizontals=ffts)
            ver = ffts["vt"]
            del ffts
        elif method == "azimuth":
            hor = self.combine_horizontals(method=method,
                                           horizontals={"ew": self.ew,
                                                        "ns": self.ns},
                                           azimuth=azimuth)
            if isinstance(hor, WindowedTimeSeries):
                hor = FourierTransformSuite.from_timeseries(hor)
                ver = FourierTransformSuite.from_timeseries(self.vt)
            elif isinstance(hor, TimeSeries):
                hor = FourierTransform.from_timeseries(hor)
                ver = FourierTransform.from_timeseries(self.vt)
            else:
                raise NotImplementedError
        else:
            msg = f"`method`={method} has not been implemented."
            raise NotImplementedError(msg)

        if resampling["res_type"] == "linear":
            frq = np.linspace(resampling["minf"],
                              resampling["maxf"],
                              resampling["nf"])
        elif resampling["res_type"] == "log":
            frq = np.geomspace(resampling["minf"],
                               resampling["maxf"],
                               resampling["nf"])
        else:
            raise NotImplementedError

        hor.smooth_konno_ohmachi_fast(frq, bandwidth)
        ver.smooth_konno_ohmachi_fast(frq, bandwidth)
        hor.amp /= ver.amp
        hvsr = hor
        del ver

        if self.ns.n_windows == 1:
            window_length = max(self.ns.time)
        else:
            window_length = max(self.ns.time[0])

        if isinstance(self.meta, dict):
            self.meta["Window Length"] = window_length
        else:
            self.meta = {"Window Length": window_length}

        return Hvsr(hvsr.amp, hvsr.frq, find_peaks=False, meta=self.meta)

    def __iter__(self):
        """Iterable representation of a Sensor3c object."""
        return iter((self.ns, self.ew, self.vt))
