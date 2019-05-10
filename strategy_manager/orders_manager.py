#!/usr/bin/env python3
# coding: utf-8
# @Author: ArthurBernard
# @Email: arthur.bernard.92@gmail.com
# @Date: 2019-04-29 23:42:09
# @Last modified by: ArthurBernard
# @Last modified time: 2019-05-10 20:21:05

""" Manage orders execution. """

# Built-in packages
from pickle import Pickler, Unpickler
import logging
import time

# External packages
from requests import HTTPError

# Internal packages
from strategy_manager.tools.time_tools import now
from strategy_manager.API_kraken import KrakenClient
from strategy_manager.data_requests import get_close

__all__ = ['SetOrder']

"""
TODO list:
    - New method : set history orders
    - New method : get available funds
    - New method : verify integrity of new orders
    - New method : (future) split orders for a better scalability
"""


class SetOrder:
    """ Class to set and manage orders.

    Verify the intigrity of the new orders with past orders and suffisant
    funds.
    An id order is a signed integer smaller than 32-bit, three last number
    correspond to the id strategy and the other numbers correspond to an id
    user. The id user is in fact an id time, it corresponding at the number
    of minutes since a starting point saved in the file 'id_timestamp'. The
    file 'id_timestamp' will be reset every almost three years.

    Methods
    -------
    order(**kwargs)
        Request an order (with krakenex in first order).
    get_query_order(id_order)
        Return status of a specified order or position.
    # TODO : cancel orders/position if too far of mid
    # TODO : replace limit order/position
    # TODO : market order/position if time is over

    Attributs
    ---------
    id_strat : int (signed and max 32-bit)
        Number to identify an order and link it with a strategy.
    id_max : int
        Number max for an id_order (32-bit).
    path : str
        Path where API key and secret are saved.
    K : API
        Object to query orders on Kraken exchange.
    current_pos : float
        The currently position, {-1: short, 0: neutral, 1: long}.

    """

    def __init__(self, id_strat, path_log, current_pos=0, current_vol=0,
                 exchange='kraken', frequency=1):
        """ Set the order class.

        Parameters
        ----------
        id_strat : int (unsigned and 32-bit)
            Number to link an order with a strategy.
        path_log : str
            Path where API key and secret are saved.
        current_pos : int, {1 : long, 0 : None, -1 : short}
            Current position of the account.
        current_vol : float
            Current volume position.
        exchange : str, optional
            Name of the exchange (default is `'kraken'`).
        frequency : int, optional
            Frequency to round timestamp.

        """
        self.id_strat = id_strat
        self.id_max = 2147483647
        self.path = path_log
        self.current_pos = current_pos
        self.current_vol = current_vol
        self.frequency = frequency
        self.start = int(time.time())

        self.logger = logging.getLogger('strat_man.' + __name__)

        if exchange.lower() == 'kraken':
            self.K = KrakenClient()
            self.K.load_key(path_log)
            self.fees_dict = self.K.query_private(
                'TradeVolume',
                pair='all'
            )['result']

        else:
            self.logger.error('Exchange "{}" not allowed'.format(exchange))

            raise ValueError(exchange + ' not allowed.')

    def order(self, id_order=None, **kwargs):
        """ Request an order following defined parameters.

        /! To verify ConnectionResetError exception. /!

        Parameters
        ----------
        kwargs : dict
            Parameters for ordering, refer to API documentation of the
            plateform used.

        Return
        ------
        out : json
            Output of the request.

        """
        if id_order is None:
            id_order = self._set_id_order()

        if kwargs['leverage'] == 1:
            kwargs['leverage'] = None

        # TODO : Append a method to verify if the volume is available.
        try:
            # Send order
            out = self.K.query_private(
                'AddOrder',
                userref=id_order,
                timeout=30,
                **kwargs
            )
            self.logger.info(out['result']['descr']['order'])

        except Exception as e:

            if e in [HTTPError]:
                self.logger.error('Catching the following error: {}'.format(e))

            else:
                self.logger.error('Unknown error: {}'.format(type(e)),
                                  exc_info=True)

                raise e

        # Verify if order is posted
        post_order = self.verify_post_order(id_order)
        if not post_order and not kwargs['validate']:
            self.logger.info('Order not posted. Bot will retry.')
            time.sleep(1)

            return self.order(id_order=id_order, **kwargs)

        return self._set_result_output(out, id_order, **kwargs)

    def verify_post_order(self, id_order):
        """ Verify if an order is well posted.

        Parameters
        ----------
        id_order : int
            User reference of the order to verify.

        Returns
        -------
        bool :
            Return true if order is posted else false.

        """
        open_order = self.K.query_private('OpenOrders', userref=id_order)
        if open_order['result']['open']:

            return True

        closed_order = self.K.query_private('ClosedOrders',
                                            userref=id_order, start=self.start)
        if closed_order['result']['closed']:

            return True

        return False

    def _set_result_output(self, out, id_order, **kwargs):
        """ Add informations to output of query order. """
        # Set infos
        out['result']['userref'] = id_order
        out['result']['timestamp'] = now(self.frequency)
        out['result']['fee'] = self._get_fees(
            kwargs['pair'],
            kwargs['ordertype']
        )
        if kwargs['ordertype'] == 'market' and kwargs['validate']:
            # Get the last price
            out['result']['price'] = get_close(kwargs['pair'])

        elif kwargs['ordertype'] == 'market' and not kwargs['validate']:
            # TODO : verify if get the exection market price
            closed_order = self.K.query_private('ClosedOrders',
                                                userref=id_order,
                                                start=self.start)['result']
            txid = out['result']['txid']
            out['result']['price'] = closed_order['closed'][txid]['price']
            self.logger.debug('Get execution price is not yet verified')

        return out

    def set_order(self, signal, **kwargs):
        """ Set parameters to order.

        Parameters
        ----------
        signal : int, {1 : long, 0 : None, -1 : short}
            Signal of strategy.
        kwargs : dict
            Parameters for ordering.

        Returns
        -------
        out : list
            Orders answere.

        """
        out = []

        # Don't move
        if self.current_pos == signal:

            return [self._set_output(kwargs)]

        # Up move
        elif self.current_pos <= 0. and signal >= 0:
            kwargs['type'] = 'buy'
            out += [self.cut_short(signal, **kwargs.copy())]
            out += [self.set_long(signal, **kwargs.copy())]

        # Down move
        elif self.current_pos >= 0. and signal <= 0:
            kwargs['type'] = 'sell'
            out += [self.cut_long(signal, **kwargs.copy())]
            out += [self.set_short(signal, **kwargs.copy())]

        return out

    def cut_short(self, signal, **kwargs):
        """ Cut short position. """
        if self.current_pos < 0:
            # Set leverage to cut short
            leverage = kwargs.pop('leverage')
            leverage = 2 if leverage is None else leverage + 1

            # Set volume to cut short
            kwargs['volume'] = self.current_vol

            # Query order
            out = self.order(leverage=leverage, **kwargs)

            # Set current volume and position
            self.current_vol = 0.
            self.current_pos = 0
            out['result']['current_volume'] = 0.
            out['result']['current_position'] = 0

        else:
            out = self._set_output(kwargs)

        return out

    def set_long(self, signal, **kwargs):
        """ Set long order. """
        if signal > 0:
            out = self.order(**kwargs)

            # Set current volume
            self.current_vol = kwargs['volume']
            self.current_pos = signal
            out['result']['current_volume'] = self.current_vol
            out['result']['current_position'] = signal

        else:
            out = self._set_output(kwargs)

        return out

    def cut_long(self, signal, **kwargs):
        """ Cut long position. """
        if self.current_pos > 0:
            # Set volume to cut long
            kwargs['volume'] = self.current_vol
            out = self.order(**kwargs)

            # Set current volume
            self.current_vol = 0.
            self.current_pos = 0
            out['result']['current_volume'] = 0.
            out['result']['current_position'] = 0

        else:
            out = self._set_output(kwargs)

        return out

    def set_short(self, signal, **kwargs):
        """ Set short order. """
        if signal < 0:
            # Set leverage to short
            leverage = kwargs.pop('leverage')
            leverage = 2 if leverage is None else leverage + 1
            out = self.order(leverage=leverage, **kwargs)

            # Set current volume
            self.current_vol = kwargs['volume']
            self.current_pos = signal
            out['result']['current_volume'] = self.current_vol
            out['result']['current_position'] = signal

        else:
            out = self._set_output(kwargs)

        return out

    def _set_output(self, kwargs):
        """ Set output when no orders query. """
        out = {
            'result': {
                'timestamp': now(self.frequency),
                'current_volume': self.current_vol,
                'current_position': self.current_pos,
                'fee': self._get_fees(kwargs['pair'], kwargs['ordertype']),
                'descr': None,
            }
        }
        if kwargs['ordertype'] == 'limit':
            out['result']['price'] = kwargs['price']

        elif kwargs['ordertype'] == 'market':
            out['result']['price'] = get_close(kwargs['pair'])

        else:
            raise ValueError(
                'Unknown order type: {}'.format(kwargs['ordertype'])
            )

        return out

    def get_query_order(self, id_order):
        """ Return query order of a specified id order.

        Parameters
        ----------
        id_order : int (signed and 32-bit)
            Number to link an order with strategy, time and other.

        Returns
        -------
        str
            Query of specified order.

        """
        try:
            ans = self.K.query_private(
                'OpenOrders',
                trades=True,
                userref=id_order,
            )

            return ans['result']

        except Exception as e:

            if e in [HTTPError]:
                self.logger.error('Catching the following error: {}'.format(e))

                return self.get_status_order(id_order)

            else:
                self.logger.error(
                    'UNKNOWN ERROR : {}\nAnswere of query: {}'.format(
                        type(e),
                        ans
                    ),
                    exc_info=True
                )

                raise e

    def _get_fees(self, pair, order_type):
        """ Get current fees of order.

        Parameters
        ----------
        pair : str
            Symbol of the currency pair.
        order_type : str
            Type of order.

        Returns
        -------
        float
            Fees of specified pair and order type.

        """
        if order_type == 'market':

            return float(self.fees_dict['fees'][pair]['fee'])

        elif order_type == 'limit':

            return float(self.fees_dict['fees_maker'][pair]['fee'])

        else:

            raise ValueError('Unknown order type: {}'.format(order_type))

    def _set_id_order(self):
        """ Set an unique order identifier.

        Returns
        -------
        id_order : int (signed and 32-bit)
            Number to identify an order and link it with a strategy.

        """
        try:

            with open('id_order.dat', 'rb') as f:
                id_order = Unpickler(f).load()

        except FileNotFoundError:
            id_order = 0

        id_order += 1
        if id_order > self.id_max // 100:
            id_order = 0

        with open('id_order.dat', 'wb') as f:
            Pickler(f).dump(id_order)

        return int(str(id_order) + str(self.id_strat))
