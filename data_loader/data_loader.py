#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pickle import Pickler, Unpickler
import time

"""
TODO list:
    - 
"""

class DataLoader:
    """
    Description..
    Read, sort and clean data and get ready to send to strategy manager.

    Methods
    -------
    todo: - Load data;
          - Sort and clean data;
          - Get ready data;
          - to finish: transform date to timestampe;

    Attributes
    ----------

    """
    def __init__(self, timestep, underlying, sample_size=None, since=None, last=None):
        """
        Parameters
        ----------
        :timestep: int
            Number of seconds between two samples.
        :underlying: str or list ?
            Name of the underlying or list of data needed.
        :sample_size: int (default is None)
            Size of data sample needed.
        :since: data (%d-%m-%y %H:%M:%S) or timestamp.
            Date of first observation of data sample (default is the first 
            observation of the day). This parameter is ignored if sample_size 
            is specified.
        :last: data (%d-%m-%y %H:%M:%S) or timestamp.
            Date of last observation of data sample (default is now).
        """
        self.timestep = timestep
        self.underlying = underlying
        self.last = self._date_to_TS(last)
        if sample_size is not None:
            self.since = self.last - timestep * sample_size
        elif since is not None:
            self.since = self._date_to_TS(since)
        else:
            sample_size = (last % 86400) * 86400
            self.since = self.last - timestep * sample_size
        
    def _date_to_TS(self, date):
        """
        Parameters
        ----------
        :date: int, str, date, etc ?
            Date to convert in timestamp

        Return
        ------
        Timestamp of the date.
        """
        if isinstance(date, int):
            return date
        elif isinstance(date, str):
            pass
        else:
            print('Date format not allowed')
            raise Error