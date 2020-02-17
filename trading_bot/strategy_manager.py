#!/usr/bin/env python3
# coding: utf-8
# @Author: ArthurBernard
# @Email: arthur.bernard.92@gmail.com
# @Date: 2019-05-12 22:57:20
# @Last modified by: ArthurBernard
# @Last modified time: 2020-02-17 16:03:31

""" Client to manage a financial strategy. """

# Built-in packages
import time
import importlib
import logging
from os import getpid, getppid
import sys

# External packages

# Local packages
# from strategy_manager import DataBaseManager, DataExchangeManager
from trading_bot.data_requests import get_close
from trading_bot.tools.time_tools import now, str_time
from trading_bot.tools.utils import load_config_params, dump_config_params
from trading_bot._client import _BotClient

__all__ = ['StrategyManager']


class StrategyManager(_BotClient):
    """ Main object to load data, compute signals and execute orders.

    Methods
    -------
    get_order_params(data)
        Computes and returns signal strategy and additional parameters to set
        order.
    __call__(*args, **kwargs)
        Set parameters to pass into function' strategy.
    set_iso_vol(series, target_vol=0.2, leverage=1., period=252, half_life=11)
        Computes and returns iso-volatility coefficient.
    get_order_params(data, *args, **kwargs)
        Function to get signal strategy and additional parameters to set order.
        `data` must be a pd.DataFrame, `*args` and `**kwargs` can be any
        parameters.

    Attributes
    ----------
    get_order_params : callable
        Strategy function that returns a tuple with a signal ({1, 0, -1}) and
        additional parameters (dict) to set order.
    name_strat : str
        Name of the strategy to run.
    STOP : int, optional
        Number of iteration before stoping, if None it will load it in
        configuration file.
    path : str, optional
        Path of the folder to load the strategy and configuration file.
    frequency : int
        Number of seconds between two samples.

    """

    # TODO : Load strategy config
    def __init__(self, address=('', 50000), authkey=b'tradingbot'):
        """ Initialize strategy manager.

        Parameters
        ----------
        address :
        authkey :

        """
        # Set client and connect to the trading bot server
        _BotClient.__init__(self, address=address, authkey=authkey)
        self.logger = logging.getLogger(__name__ + '.StrategyManager')
        self.logger.info('init | PID: {} PPID: {}'.format(getpid(), getppid()))

    def __call__(self, name_strat, STOP=None, path='./strategies'):
        """ Set parameters of strategy.

        Parameters
        ----------
        name_strat : str
            Name of the strategy to run.
        STOP : int, optional
            Number of iteration before stoping, if None it will load it in
            configuration file.
        path : str, optional
            Path of the folder to load the strategy.

        Returns
        -------
        StrategyManager
            Object to manage strategy computations.

        """
        # Import strategy
        strat = importlib.import_module(
            'strategies.' + name_strat + '.strategy'
        )
        self.get_order_params = strat.get_order_params
        self.logger.info('call | Load {} function'.format(name_strat))

        self.name_strat = name_strat
        self.STOP = STOP
        self.path = path + '/' + name_strat

        return self

    def __iter__(self):
        """ Initialize iterative method. """
        self.t = 0
        self.TS = now(self.frequency)
        self.next = self.TS + self.frequency
        self.logger.info('iter | Start now and stop in {}'.format(
            str_time(int(self.time_stop()))
        ))

        return self

    def __next__(self):
        """ Iterate method.

        Returns
        -------
        list
            If the position moved then return the list of executed orders,
            otherwise returns an empty list.

        """
        server_stop = self.is_stop()
        strat_stop = self.t >= self.STOP
        if server_stop or strat_stop:
            self.logger.debug('next | Server stop : {}'.format(server_stop))
            self.logger.debug('next | Strategy stop : {}'.format(strat_stop))

            raise StopIteration

        self.TS = int(time.time())
        if self.next <= self.TS:
            self.next += self.frequency
            self.t += 1
            self.logger.info('next | {}/{}iteration'.format(self.t, self.STOP))
            self.logger.info('next | Stop in {}'.format(
                str_time(int(self.time_stop()))
            ))
            # TODO : Debug/find solution to request data correctly.
            #        Need to choose between request a database, server,
            #        exchange API or other.
            data = self.DM.get_data(*self.args_data, **self.kwargs_data)

            return self.get_order_params(data, *self.f_args, **self.f_kwrds)

        return None, None

    def __enter__(self):
        """ Enter. """
        # TODO : Load precedent data
        self.logger.info('enter | Load configuration and history')
        self.set_config(self.path + '/configuration.yaml')
        # self.get_histo_orders(self.path + '/orders_hist.dat')
        # self.get_histo_result(self.path + '/result_hist.dat')

        return self

    def set_config(self, path):
        """ Set configuration.

        Parameters
        ----------
        path : str
            Path to load the YAML configuration file.

        """
        self.logger.info('set_config | Strat {}'.format(self.name_strat))
        self.cfg = load_config_params(path)
        # Set general configuration
        self._get_general_cfg(self.cfg['strat_manager_instance'])
        # Set data manager configuration
        self.set_data_manager(**self.cfg['get_data_instance'].copy())
        # Set stategy parameters
        self._strat_cfg(self.cfg['strategy_instance'])
        # Set parameters for orders
        self.ord_kwrds = self.cfg['order_instance']
        # TODO : Set ResultManager
        self.logger.info('set_config | Strategy is configured')

    def _get_general_cfg(self, strat_cfg):
        # Get general parameters and strategy state
        self.frequency = strat_cfg['frequency']
        self.id_strat = strat_cfg['id_strat']
        name_logger = __name__ + '.Strat-' + str(self.id_strat)
        self.logger = logging.getLogger(name_logger)
        self.current_pos = strat_cfg['current_pos']
        self.current_vol = strat_cfg['current_vol']
        self.logger.info('_get_general_cfg | pos: {}'.format(self.current_pos))
        self.logger.info('_get_general_cfg | vol: {}'.format(self.current_vol))
        if self.STOP is None:
            self.STOP = strat_cfg['STOP']

    def set_general_cfg(self, path):
        """ Save configuration with respect to new position and volume.

        Parameters
        ----------
        path : str
            path to save the configuration file.

        """
        self.cfg['strat_manager_instance']['current_pos'] = self.current_pos
        self.cfg['strat_manager_instance']['current_vol'] = self.current_vol
        self.logger.info('set_general_cfg | pos: {}'.format(self.current_pos))
        self.logger.info('set_general_cfg | vol: {}'.format(self.current_vol))
        dump_config_params(self.cfg, path)

    def _strat_cfg(self, strat_cfg):
        # Set parameters for strategy function
        self.f_args = strat_cfg['args_params']
        self.f_kwrds = strat_cfg['kwargs_params']

    def __exit__(self, exc_type, exc_value, exc_tb):
        """ Exit. """
        self.logger.info('exit | Save configuration')
        # Save configuration and data
        self.set_general_cfg(self.path + '/configuration.yaml')
        # TODO: Save data
        # self.set_histo_orders(self.path + '/orders_hist.dat')
        # self.set_histo_result(self.path + '/result_hist.dat')
        if exc_type is not None:
            self.logger.error('exit | {}: {}\n{}'.format(
                exc_type, exc_value, exc_tb
            ))

        self.logger.info('exit | end')

    def set_order(self, s, **kwargs):
        """ Compute signal and additional parameters to set order.

        Parameters
        ----------
        s : {-1, 0, 1}
            Signal of strategy.
        **kwargs : keyword arguments
            Parameters for order, e.g. volume, order type, etc.

        """
        out = []
        # Up move
        if self.current_pos <= 0. and s >= 0 and self.current_pos != s:
            kwargs['type'] = 'buy'
            if self.current_pos < 0:
                out += self._cut_short(s, **kwargs.copy())

            if s > 0:
                out += self._set_long(s, **kwargs.copy())

        # Down move
        elif self.current_pos >= 0. and s <= 0 and self.current_pos != s:
            kwargs['type'] = 'sell'
            if self.current_pos > 0:
                out += self._cut_long(s, **kwargs.copy())

            if s < 0:
                out += self._set_short(s, **kwargs.copy())

        return out

    def _cut_short(self, signal, **kwargs):
        """ Cut short position. """
        # Set leverage to cut short
        leverage = kwargs.pop('leverage')
        kwargs['leverage'] = 2 if leverage is None else leverage + 1

        # Set volume to cut short
        kwargs['volume'] = self.current_vol

        # Query order
        result = self.send_order(**kwargs)

        # Set current volume and position
        self.current_vol = 0.
        self.current_pos = 0.
        result['current_volume'] = 0.
        result['current_position'] = 0.
        self.logger.info('_cut_short | pos: {}'.format(self.current_pos))

        return [result]

    def _set_long(self, signal, **kwargs):
        """ Set long order. """
        result = self.send_order(**kwargs)

        # Set current volume
        self.current_vol = kwargs['volume']
        self.current_pos = float(signal)
        result['current_volume'] = self.current_vol
        result['current_position'] = signal
        self.logger.info('_set_long | pos: {}'.format(self.current_pos))

        return [result]

    def _cut_long(self, signal, **kwargs):
        """ Cut long position. """
        # Set volume to cut long
        kwargs['volume'] = self.current_vol

        # Query order
        result = self.send_order(**kwargs)

        # Set current volume
        self.current_vol = 0.
        self.current_pos = 0.
        result['current_volume'] = 0.
        result['current_position'] = 0.
        self.logger.info('_cut_long | pos: {}'.format(self.current_pos))

        return [result]

    def _set_short(self, signal, **kwargs):
        """ Set short order. """
        # Set leverage to short
        leverage = kwargs.pop('leverage')
        kwargs['leverage'] = 2 if leverage is None else leverage + 1
        result = self.send_order(**kwargs)

        # Set current volume
        self.current_vol = kwargs['volume']
        self.current_pos = float(signal)
        result['current_volume'] = self.current_vol
        result['current_position'] = signal
        self.logger.info('_set_short | pos: {}'.format(self.current_pos))

        return [result]

    def send_order(self, **kwargs):
        """ Send the ID of strategy and order parameters to OrdersManager.

        Parameters
        ----------
        **kwargs : keyword arguments
            Parameters for order, e.g. volume, order type, etc.

        """
        self.q_ord.put((self.id_strat, kwargs))
        self.logger.info('send_order | Params {}'.format(kwargs))

        return self._set_output(kwargs)

    def _set_output(self, kwargs):
        """ Set output when no orders query. """
        result = {
            'timestamp': now(self.frequency),
            'current_volume': self.current_vol,
            'current_position': self.current_pos,
            'fee': self.get_fee(kwargs['pair'], kwargs['ordertype']),
            'descr': None,
        }
        if kwargs['ordertype'] == 'limit':
            result['price'] = kwargs['price']

        elif kwargs['ordertype'] == 'market':
            # TODO : Improve it
            #    request close price to OM ? TBM ? DM ?
            result['price'] = get_close(kwargs['pair'])

        else:
            raise ValueError(
                'Unknown order type: {}'.format(kwargs['ordertype'])
            )

        return result

    def set_data_manager(self, **kwargs):
        """ Set `DataManager` object.

        Parameters
        ----------
        kwargs : dict
            Cf `DataManager` constructor.

        """
        if 'args' in kwargs.keys():
            self.args_data = kwargs.pop('args')
        else:
            self.args_data = ()

        if 'kwargs' in kwargs.keys():
            self.kwargs_data = kwargs.pop('kwargs')
        else:
            self.kwargs_data = {}

        request_from = kwargs.pop('source_data').lower()
        self.DM = self._handler[request_from](**kwargs)
        self.logger.info('set_data_manager | {} init'.format(request_from))

        return self

    def time_stop(self):
        """ Compute the number of seconds before stopping.

        Returns
        -------
        int
            Number of seconds before stopping.

        """
        time_stop = (self.STOP - self.t) * self.frequency

        return max(time_stop - time.time() % self.frequency, 0)

    def start_loop(self):
        """ Run a loop until condition is false. """
        for s, kw in self:
            if s is not None:
                self.logger.info('Signal: {} | Parameters: {}'.format(s, kw))
                output = self.set_order(s, **kw, **self.ord_kwrds)
                if output:
                    self.logger.info('Executed order : {}'.format(output))

            txt = '{} | Next signal in {:.1f}'.format(
                time.strftime('%y-%m-%d %H:%M:%S'),
                str_time(self.next - self.TS),
            )
            print(txt, end='\r')
            time.sleep(0.01)

        self.logger.info('StrategyManager stopped.')


if __name__ == '__main__':

    import logging.config
    import yaml

    with open('./trading_bot/logging.ini', 'rb') as f:
        config = yaml.safe_load(f.read())

    logging.config.dictConfig(config)

    if len(sys.argv) < 2:
        print('/!\\ RUN ANOTHER_EXAMPLE_2 /!\\')
        name = 'another_example_2'

    else:
        name = sys.argv[1]

    sm = StrategyManager()
    with sm(name):
        # sm.set_config('./strategies/' + name + '/configuration.yaml')
        for s, kw in sm:
            if s is not None:
                sm.logger.info(' | Signal: {} | Parameters: {}'.format(s, kw))
                output = sm.set_order(s, **kw, **sm.ord_kwrds)

                if output:
                    sm.logger.info(' | Executed order : {}'.format(output))

            txt = time.strftime('%y-%m-%d %H:%M:%S')
            txt += ' | Next signal in {:.1f}'.format(sm.next - time.time())
            print(txt, end='\r')
            time.sleep(0.01)

        sm.logger.info('StrategyManager stopped.')

    print('bye')
