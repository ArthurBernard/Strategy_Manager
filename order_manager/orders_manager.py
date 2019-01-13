#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Import built-in packages
from pickle import Pickler, Unpickler
import time

# Import external package(s)
from krakenex import API

"""
TODO list:
    - Finish the method 'order'
    - New method : set history orders
    - New method : get pending orders
    - New method : get available funds
    - New method : verify integrity of new orders
    - New method : (future) split orders for a better scalability
"""


class SetOrder:
    """
    Class to set and manage orders. Verify the intigrity of the new orders 
    with past orders and suffisant funds.

    An id order is a signed integer smaller than 32-bit, three last number
    correspond to the id strategy and the other numbers correspond to an id
    user. The id user is in fact an id time, it corresponding at the number
    of minutes since a starting point saved in the file 'id_timestamp'. The
    file 'id_timestamp' will be reset every almost three years.

    Methods
    -------
    - order : Request an order (with krakenex in first order).
    - decode_id_order : Takes an id order and returns the corresponding id 
    strategy and timestamp.

    Attributs
    ---------
    :id_strat: int (signed and max 32-bit)
        Number to link an order with a strategy.
    :id_max: int
        Number max for an id_order (32-bit).
    :path: str
        Path where API key and secret are saved.
    """
    def __init__(self, id_strat, path):
        """
        Set the order class.

        Parameters
        ----------
        :id_strat: int (unsigned and 32-bit)
            Number to link an order with a strategy.
        :path: str
            Path where API key and secret are saved.
        """
        self.id_strat = id_strat
        self.id_max = 2147483647
        self.path = path
        # Use krakenex API while i am lazy to do myself
        self.K = API()
        self.K.load_key(path)

    def order(self, **kwargs):
        """
        Request an order following defined parameters.

        /! To verify ConnectionResetError exception. /!

        Parameters
        ----------
        :kwargs: parameters for ordering, refer to API documentation of the 
        plateform used.

        Return
        ------
        :out: json
            Output of the request.
        """
        id_order = self._set_id_order()
        # /! Append a method to verify if the volume is available. /!
        try:
            out = self.K.query_private('AddOrder', {**kwargs, 'userref': id_order})
        except timeout:
            print('timeout error')
            out = self.order(**kwargs)
        except ConnectionResetError:
            self = SetOrder(self.id_strat, self.path) # Verify if it's working
            out = self.order(**kwargs)
        return out

    def _set_id_order(self):
        """ 
        Set an identifier for an order according with the strategy 
        reference, time and optional id parameters.

        Returns
        -------
        :id_order: int (signed and 32-bit)
            Number to link an order with strategy, time and other.
        """
        id_user = self._get_id_user()
        id_order = int(str(id_user)+str(self.id_strat))
        return id_order

    def _get_id_user(self):
        """
        Get id user in function of a time starting point (in minutes). Time 
        starting point restart from 0 every almost 3 years. 

        Returns
        -------
        :id_user: int (signed and less than 32-bit)
            Number to link an order with a time.
        """
        try:
            f = open('id_timestamp', 'rb')
            TS = Unpickler(f).load()
            f.close()
        except FileNotFoundError:
            TS = 0
        now = int(time.time())
        id_user = (now - TS) // 60 
        if id_user > self.id_max // 1000:
            f = open('id_timestamp', 'wb')
            Pickler(f).dump(now)
            f.close()
            id_user = self._get_id_user()
        return id_user
    
    def decode_id_order(self, id_order):
        """
        From an id order decode the time (in minute) and the strategy 
        corresponding to the order.
        
        Parameters
        ----------
        :id_order: int (signed and 32-bit)
            Number to link an order with strategy, time and other.

        Returns
        -------
        :TS: int (signed)
            Timestamp at the passing order.
        :id_strat: int (unsigned and 32-bit)
            Number to link an order with a strategy.
        """
        id_user = id_order // 1000
        id_strat = id_order % 1000
        f = open('id_timestamp', 'rb')
        TS = Unpickler(f).load() + id_user * 60
        f.close()
        return TS, id_strat
