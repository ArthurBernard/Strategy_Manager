#!/usr/bin/env python3
# coding: utf-8
# @Author: ArthurBernard
# @Email: arthur.bernard.92@gmail.com
# @Date: 2020-02-06 11:57:48
# @Last modified by: ArthurBernard
# @Last modified time: 2020-02-17 19:12:23

""" Some order objects. """

# Built-in packages
import time
import logging

# Third party packages

# Local packages
from trading_bot._exceptions import OrderError, OrderStatusError
from trading_bot.data_requests import get_ask, get_bid, get_close

__all__ = ['Order', 'OrderDict']


class Order:
    """ Order object.

    Methods
    -------
    execute
    cancel
    get_open
    get_closed
    get_vol_exec
    check_vol_exec
    replace

    Attributes
    ----------
    id : int
        ID of the order (32-bit).
    exchange_client : object inherits from ExchangeClient
        API client to send private requests.
    status : {None, 'open', 'canceled', 'closed'}
        Status of the order.
    input : dict
        Parameters of the order to sent.
    volume : float
        Initial volume to order.
    type : {'buy', 'sell'}
        Type of the order.
    vol_exec : float
        Current volume executed.
    pair : str
        Code corresponding to the pair of the order.
    price : float or 'market'
        Price to sent to the order.
    state : dict
        Last state of the order (ansewered by the exchange API).
    history : list of dict
        Historic of all anseweres by the exchange API.
    tol : float, optional
            Tolerance's threshold for non-executed volume. Default is 0.1%.

    """

    _handler_best = {
        'buy': get_bid,
        'sell': get_ask,
    }

    def __init__(self, id, exchange_client, status=None, input={}, tol=0.001,
                 call_counter=None):
        """ Initialize an order object.

        Parameters
        ----------
        id : int
            ID of the order (32-bit signed integer).
        exchange_client : ExchangeClient
            Object to connect with the client API of the exchange.
        status : {'open', 'closed', 'canceled', None}
            State of the order:
            - If None (default), then the order never been executed.
            - If 'open', then the order was send.
            - If 'closed', then the order was sent and all the initial volume
            was executed.
            - If 'canceled', then the order was canceled and only the quantity
            of `volume` wasn't executed.
        input : dict, optional
            Input to request order.
        tol : float, optional
            Tolerance's threshold for non-executed volume. Default is 0.1%.
        call_counter : CallCounter, optional
            Object that calls itself at each private request, and if call rate
            limit is exceeded then the object waits a few seconds. By default
            the object is None, so it never waits.

        """
        self.logger = logging.getLogger(__name__ + '.Ord-' + str(id))
        self.id = id
        self.exchange_client = exchange_client
        self.status = status
        self.input = input
        self.tol = tol

        if call_counter is None:
            self.call_counter = lambda x: None

        else:
            self.call_counter = call_counter

        self.volume = input['volume']
        self.type = input['type']
        self.vol_exec = 0.
        self.price_exec = 0.
        self.pair = input['pair']

        if input['ordertype'] == 'market':
            self.price = 'market'

        else:
            self.price = input['price']

        if self.input['leverage'] == 1:
            self.input['leverage'] = None

        self._start = int(time.time())
        self.state = None
        self.hist = []
        self.logger.debug('init')

    def __repr__(self):
        """ Represent the order. """
        return ("[Order ID {self.id}] - status: {self.status}, type: "
                "{self.type}, pair: {self.pair}, price: {self.price}, volume: "
                "{self.volume}, vol_exec: {self.vol_exec}".format(self=self))

    def execute(self):
        """ Execute the order. """
        if self.status is None or self.status == 'canceled':
            self._last = int(time.time())
            ans = self._request('AddOrder', userref=self.id, **self.input)
            self.state = ans
            if self.input.get('validate'):
                self.logger.debug('execute | validate order')
                self.status = 'closed'
                if self.price == 'market':
                    self.price = get_close(self.pair)
                    self.logger.debug('execute | set price {}'.format(self.price))

            else:
                self.status = 'open'

        else:
            raise OrderStatusError(self, 'execute')

    def cancel(self):
        """ Cancel the order. """
        if self.status == 'open':
            ans = self._request('CancelOrder', txid=self.id)
            if ans['count'] == 0:

                raise OrderError(self, 'no order canceled')

            else:
                self.status = 'canceled'

                return ans

        else:

            raise OrderStatusError(self, 'cancel')

    def get_closed(self, start):
        """ Get the closed orders corresponding to the ID.

        Parameters
        ----------
        start : int
            Timestamp from which requested closed orders.

        Returns
        -------
        dict
            Closed orders.

        """
        return self._request('ClosedOrders', userref=self.id, start=start)

    def get_open(self):
        """ Get the open orders corresponding to the ID.

        Returns
        -------
        dict
            Open orders.

        """
        return self._request('OpenOrders', userref=self.id)

    def get_vol_exec(self, start):
        """ Get the volume executed since `start` parameter.

        Parameters
        ----------
        start : int
            Timestamp from which requested volume executed.

        Returns
        -------
        float
            Executed volume.

        """
        vol_exec = 0.
        ans = self.get_closed(start=start)
        for v in ans['closed'].values():
            vol_exec += v['vol_exec']

        return vol_exec

    def check_vol_exec(self):
        """ Check the volume has been executed. """
        if self.status is None:

            raise OrderStatusError(self, 'check_vol_exec')

        self._update_vol_exec()

        if self.vol_exec == self.volume:
            self.status = 'closed'
            self.logger.debug('check_vol_exec | order closed')

        elif 1 - self.vol_exec / self.volume < self.tol:
            self.status = 'closed'
            not_exec_vol = 1 - self.vol_exec / self.volume
            self.logger.warning("{:.6%} of the volume was not executed but is "
                                "less than tolerance's threshold {:%}"
                                "".format(not_exec_vol, self.tol))

        elif self.vol_exec > self.volume:

            raise OrderError(self, msg_prefix='too many volume executed: ')

        else:
            self.logger.debug('check_vol_exec | ex vol={}, new vol={}'.format(
                self.input['volume'], self.volume - self.vol_exec
            ))
            self.input['volume'] = self.volume - self.vol_exec

    def replace(self, price):
        """ Cancel the open or pending order and add a new order.

        The new order fill the non-executed volume and it add at the specified
        price, if price is None the order will be at the market price or if the
        is "best" then the order will be add at the best ask/bid price.

        Parameters
        ----------
        price : float or {'best', 'market'}
            Price to add the new order. If 'market' then the order will be at
            market price, if 'best' then the order will be at the best ask/bid
            price.

        """
        if self.status is None or self.status == 'closed':

            raise OrderStatusError(self, 'replace')

        self.cancel()
        self.check_vol_exec()

        if price == 'market':
            self.input['type'] = 'market'
            self.input.remove('price')

        elif price == 'best':
            self.input['price'] = self._handler_best[self.type](self.pair)

        else:
            self.input['price'] = price

        self.execute()

    def _request(self, method, **kwargs):
        self.call_counter(method)
        ans = self.exchange_client.query_private(method, **kwargs)
        self.hist += [ans]
        self.logger.debug('send {} | answere: {}'.format(method, ans))

        return ans

    def _update_vol_exec(self):
        # FIXME : some issues may occurs if an order is executed between the
        # call of get_closed() and the setting of _last attribute
        ans = self.get_closed(start=self._last)
        self._last = int(time.time())
        for v in ans['closed'].values():
            self.vol_exec += v['vol_exec']

    def get_result_exec(self):
        """ Get execution information (price, fees, etc.).

        Returns
        -------
        dict
            {'txid': list, 'price': float, 'vol_exec': float, 'fee': float,
            'feeq': float, 'feeb': float, 'cost': float, 'start_time': int}.

        """
        if self.status is not 'closed':

            raise OrderStatusError(self, 'get_result_exec')

        ans = self.get_closed(start=self._start)
        self.logger.debug('get_result_exec | ' + str(ans))
        txid = list(ans['closed'].keys())
        v0, p0, f, fq, fb, c = 0., 0., 0., 0., 0., 0.
        for v in ans['closed'].values():
            if 'viqc' in v['oflags']:
                # FIXME : viqc
                raise OrderError(self, "'viqc' oflags is not yet allowed")

            oflags = get_fees_currency(v['oflags'])
            v0 += v['vol_exec']
            p0 += v['price'] * v['vol_exec']
            if oflags == 'fciq':
                fq += v['fee']

            elif oflags == 'fcib':
                fb += v['fee'] * v['price']

            f += v['fee']
            c += v['cost']

        if v0 > 0.:
            p0 /= v0

        return {
            'txid': txid,
            'price_exec': p0,
            'vol_exec': v0,
            'fee': f,
            'feeq': fq,
            'feeb': fb,
            'cost': c,
            'start_time': self._start,
        }


def get_fees_currency(oflags):
    """ Get the fees currency flags.

    Parameters
    ----------
    oflags : str or list
        Parameters returned by the exchange client API.

    Returns
    -------
    str
        'fcib' if the currency is in base, and 'fciq' if the currency is in
        quote.

    """
    if isinstance(oflags, list):
        if 'fcib' in oflags:

            return 'fcib'

        elif 'fciq' in oflags:

            return 'fciq'

        else:

            raise ValueError('unknown oflags fees: {}'.format(oflags))

    elif oflags in ['fcib', 'fciq']:

        return oflags

    else:

        raise ValueError('unknown oflags fees: {}'.format(oflags))


class OrderDict(dict):
    """ Order collection object.

    Methods
    -------
    append
    get_first
    get_ordered_list
    pop
    pop_first
    popitem
    update

    """

    _waiting, _open, _closed = [], [], []

    def __init__(self, *orders, **kworders):
        """ Initialize a collection of order objects. """
        self.logger = logging.getLogger(__name__ + '.OrderDict')
        for k, v in kworders.items():
            self._is_order(v)

        for o in orders:
            self._is_order(o)
            kworders[str(o.id)] = o

        super(OrderDict, self).__init__(**kworders)
        self._set_state()

    def __setitem__(self, key, value):
        """ Set item order.

        Parameters
        ----------
        key : int
            ID of the order.
        value : Order
            The order object to collect.

        """
        self.logger.debug('set {}'.format(key))
        self._is_order(value)
        dict.__setitem__(self, key, value)
        self._add_state(key, value)

    def __delitem__(self, key):
        """ Delete item order.

        Parameters
        ----------
        key : int
            ID of the order.

        """
        self.logger.debug('del {}'.format(key))
        dict.__delitem__(self, key)
        self._del_state(key)

    def __repr__(self):
        """ Represent the collection of orders.

        Returns
        -------
        str
            Representation of the collection of orders.

        """
        txt = 'waiting: {}, open: {}, closed: {}'.format(
            self._waiting, self._open, self._closed
        )
        txt += '\n{'
        for v in self.values():
            txt += '{},\n'.format(v)

        return txt[:-2] + '}'

    def __eq__(self, other):
        """ Compare self with other object.

        Returns
        -------
        bool
            True if self is equal to other, False otherwise.

        """
        if not isinstance(other, OrderDict):

            return False

        return (other._waiting == self._waiting and
                other._open == self._open and
                other._closed == self._closed and
                dict.__eq__(self, other))

    def append(self, order):
        """ Apend an order object to the collection.

        Parameters
        ----------
        order : Order
            Order object to append.

        """
        self._is_order(order)
        self[order.id] = order

    def get_first(self):
        """ Get the first order to sent following the priority.

        Returns
        -------
        int
            ID of the first order to sent.

        """
        ordered_list = self.get_ordered_list()

        return ordered_list[0]

    def get_ordered_list(self):
        """ Get the ordered list of orders following the priority.

        Returns
        -------
        list
            Ordered list of orders.

        """
        return self._waiting + self._open + self._closed

    def pop(self, key):
        """ Remove an order from the collection of orders.

        Parameters
        ----------
        key : int
            ID of the order to remove.

        Returns
        -------
        Order
            The removed order object.

        """
        self.logger.debug('pop {}'.format(key))
        self._del_state(key)

        return dict.pop(self, key)

    def pop_first(self):
        """ Remove the first order following the priority.

        Returns
        -------
        int
            ID of the order removed.
        Order
            Order object removed.

        """
        key = self.get_first()

        return key, self.pop(key)

    def popitem(self):
        """ Remove an random order from the collection of orders.

        Returns
        -------
        int
            ID of the order to remove.
        Order
            The removed order object.

        """
        key, value = dict.popitem(self)
        self._del_state(key)

        return key, value

    def update(self, *orders, **kworders):
        """ Update self with order objects or an other collection of orders.

        Parameters
        ----------
        *orders : Order or OrderDict
            Order objects or collection of orders to update.
        **kworders : Orders
            Order objects to update.

        """
        for k, v in kworders.items():
            self._is_order(v)

        for o in orders:
            if isinstance(o, OrderDict):
                kworders.update({k: v for k, v in o.items()})

            else:
                self._is_order(o)
                kworders[str(o.id)] = o

        dict.update(self, **kworders)
        self._reset_state()

    def _set_state(self):
        for key, value in self.items():
            self._add_state(key, value)

    def _reset_state(self):
        self._waiting, self._open, self._closed = [], [], []
        self._set_state()

    def _add_state(self, key, value):
        if value.status is None or value.status == 'canceled':
            self._waiting.append(key)

        elif value.status == 'open':
            self._open.append(key)

        elif value.status == 'closed':
            self._closed.append(key)

        else:
            raise ValueError('unknown status {}'.format(value.status))

    def _del_state(self, key):
        if key in self._waiting:
            self._waiting.remove(key)

        elif key in self._open:
            self._open.remove(key)

        elif key in self._closed:
            self._closed.remove(key)

        else:
            raise ValueError('unknown id_order: {}'.format(key))

    def _is_order(self, obj):
        if not isinstance(obj, Order):

            raise TypeError("{} must be an Order object".format(obj))

        return True
