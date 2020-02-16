#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" Handles the etherscan data and communication """

import logging
import time
import requests
from ..lib import utils
from .connector import Connector

log = logging.getLogger('crypto-exporter')


class EtherscanConnector(Connector):
    """ The EtherscanConnector class """

    settings = {}
    params = {
        'api_key': {
            'key_type': 'string',
            'default': None,
            'mandatory': True,
            'redact': True,
        },
        'addresses': {
            'key_type': 'list',
            'default': None,
            'mandatory': True,
        },
        'tokens': {
            'key_type': 'json',
            'default': None,
            'mandatory': False,
        },
        'url': {
            'key_type': 'string',
            'default': 'https://api.etherscan.io/api',
            'mandatory': False,
        },
    }

    def __init__(self, **kwargs):
        self.exchange = 'etherscan'
        self.settings = {
            'api_key': kwargs.get('api_key'),
            'url': kwargs.get("url", self.params['url']['default']),
            'addresses': kwargs.get('addresses', self.params['addresses']['default']),
            'tokens': kwargs.get('tokens', self.params['tokens']['default']),
            'enable_authentication': True
        }

        if not self.settings.get('api_key'):
            raise ValueError("Missing api_key")

    def __load_retry(self, request_data: dict, retries=5):
        """ Tries up to {retries} times to call the ccxt function and then gives up """
        data = None
        retry = True
        count = 0
        log.debug(f'Loading {request_data} with {retries} retries')
        while retry:
            try:
                count += 1
                if count > retries:
                    log.warning('Maximum number of retries reached. Giving up.')
                    log.debug(f'Reached max retries while loading {request_data}')
                else:
                    request_data.update({
                        'apikey': self.settings['api_key'],
                        'module': 'account',
                        'tag': 'latest',
                    })
                    data = requests.get(self.settings['url'], params=request_data).json()
                retry = False
            except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout,
            ) as e:
                log.warning(f"Can't connect to {self.settings['url']}. Exception caught: {utils.short_msg(e)}")
                time.sleep(1)

            if data:
                if 'NOTOK' in data.get('message'):
                    retry = True
                    if data.get('result') == 'Invalid API Key':
                        utils.authentication_error_handler(data.get('result'))
                        self.settings['enable_authentication'] = False
                        retry = False
                    data = None
                    time.sleep(1)

            if data and (data.get('message') == 'OK' or 'OK-' in data.get('message')) and data.get('result'):
                data = data.get('result')

        return data

    def _get_token_balance_on_account(self, account: str, token: dict) -> float:
        """
        gets a specific token on a specific account
        :param account The Etherium account
        :param token The token details containing `contract`, `decimals`, `short`
        :return the balance
        """
        request_data = {
            'action': 'tokenbalance',
            'contractaddress': token['contract'],
            'address': account,
        }

        balance = 0
        data = self.__load_retry(request_data)
        if data and int(data) > 0:
            decimals = 18
            if token.get('decimals', -1) >= 0:
                decimals = int(token['decimals'])
            balance = int(data) / (10**decimals) if decimals > 0 else int(data)
        return float(balance)

    def retrieve_tokens(self):
        """ Gets the tokens from an account """
        log.debug('Retrieving the tokens')
        if not self._accounts.get('ETH'):
            self._accounts.update({'ETH': {}})
        for account in self._accounts['ETH']:
            for token in self.settings['tokens']:
                if not self._accounts.get(token['short']):
                    self._accounts.update({
                        token['short']: {}
                    })
                self._accounts[token['short']].update({
                    account: self._get_token_balance_on_account(account, token)
                })

    def retrieve_accounts(self):
        """ Gets the current balance for an account """
        if self.settings['enable_authentication']:
            log.debug('Retrieving the account balances')
            request_data = {
                'action': 'balancemulti',
                'address': self.settings['addresses'],
            }
            data = self.__load_retry(request_data)
            if data:
                if not self._accounts.get('ETH'):
                    self._accounts.update({'ETH': {}})
                for account in data:
                    self._accounts['ETH'].update({
                        account['account']: float(account['balance'])/(1000000000000000000)
                    })
            if self.settings['tokens']:
                self.retrieve_tokens()
        log.debug(f'Accounts: {self._accounts}')
        return self._accounts
