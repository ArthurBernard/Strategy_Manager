#!/usr/bin/env python3
# coding: utf-8
# @Author: ArthurBernard
# @Email: arthur.bernard.92@gmail.com
# @Date: 2020-02-22 11:01:49
# @Last modified by: ArthurBernard
# @Last modified time: 2020-09-06 10:25:04

""" Module with specific containers objects. """

# Built-in packages
import logging
from pickle import Pickler, Unpickler

# Third party packages

# Local packages
from trading_bot.orders import _BasisOrder
from trading_bot._connection import _BasisConnection

__all__ = ['OrderDict', 'ConnDict']


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
        self.logger = logging.getLogger('orders_manager.container')
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
        if len(self) <= 1:
            txt += '\n{' + ',\n'.join([str(v) for v in self.values()]) + '}'

        else:
            txt += '\n{\n  '
            txt += ',\n  '.join([str(v) for v in self.values()]) + '\n}'

        return txt

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
        if not isinstance(obj, _BasisOrder):

            raise TypeError("{} must be an Order object".format(obj))

        return True

    def _load(self, path, name, ext='.dat'):
        if path[-1] != '/':
            path += '/'

        with open(path + name + ext, 'rb') as f:
            orders = Unpickler(f).load()
            for order in orders:
                if order.status != 'open':
                    continue

                order.check_vol_exec(start=order.result_exec['start_time'])

            self.update(*orders)
            # self.update(*Unpickler(f).load())

    def _save(self, path, name, ext='.dat'):
        if path[-1] != '/':
            path += '/'

        with open(path + name + ext, 'wb') as f:
            Pickler(f).dump([v for v in self.values()])


class ConnDict(dict):
    """ Connection collection object.

    Methods
    -------
    append
    get_id
    update

    """

    def __init__(self, *conn, **kwconn):
        """ Initialize a collection of connection objects. """
        self.logger = logging.getLogger(__name__)
        for k, c in kwconn.items():
            self._is_conn(c)

        for c in conn:
            if self._is_conn(c):
                kwconn[str(c.id)] = c

        super(ConnDict, self).__init__(**kwconn)

    def __setitem__(self, _id, conn):
        """ Set item Connection object.

        Parameters
        ----------
        _id : int
            ID of the Connection object.
        conn : _BasisConnection
            The Connection object to append collect.

        """
        self.logger.debug('set {}'.format(conn))
        self._is_conn(conn)
        dict.__setitem__(self, _id, conn)

    def __repr__(self):
        """ Represent the collection of connections.

        Returns
        -------
        str
            Representation of the collection of connections.

        """
        if len(self) <= 1:
            txt = ',\n'.join([str(c) for c in self.values()])

        else:
            txt = '\n  ' + ',\n  '.join([str(c) for c in self.values()]) + '\n'

        return '{' + txt + '}'

    def __eq__(self, other):
        """ Compare self with other object.

        Returns
        -------
        bool
            True if self is equal to other, False otherwise.

        """
        if not isinstance(other, ConnDict):

            return False

        return dict.__eq__(self, other)

    def append(self, conn):
        """ Apend a Connection object to the collection.

        Parameters
        ----------
        conn : _BasisConnection
            Connection object to append.

        """
        self._is_conn(conn)
        if conn.id not in self.keys():
            self[conn.id] = conn

        else:
            self.logger.error('{} is already stored'.format(conn))

            raise ValueError('{} and {}'.format(conn, self[conn.id]))

    def get_id(self, name):
        """ Get ID of a connection.

        Parameters
        ----------
        name : str
            Name of the connection.

        Returns
        -------
        int
            The ID of the connection. If `name` is not in collection then
            returns None.

        """
        for conn in self.values():
            if name == conn.name:

                return conn.id

        return None

    def update(self, *conn, **kwconn):
        """ Update self with conn objects or an other collection of conn.

        Parameters
        ----------
        *conn : _BasisConnection or ConnDict
            Connection objects or collection of conn to update.
        **kwconn : _BasisConnection
            Connection objects to update.

        """
        for k, c in kwconn.items():
            self._is_conn(c)

        for c in conn:
            if isinstance(c, ConnDict):
                kwconn.update({k: v for k, v in c.items()})

            elif self._is_conn(c):
                kwconn[str(c.id)] = c

        dict.update(self, **kwconn)

    def _is_conn(self, obj):
        if not isinstance(obj, _BasisConnection):
            self.logger.error('{} is {}'.format(obj, type(obj)))

            raise TypeError("{} must be a Connection object".format(obj))

        return True
