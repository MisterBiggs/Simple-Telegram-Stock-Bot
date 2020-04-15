import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import requests as r
from fuzzywuzzy import fuzz


class Symbol:
    """
    Functions for finding stock market information about symbols.
    """

    SYMBOL_REGEX = "[$]([a-zA-Z]{1,4})"
    LIST_URL = "http://oatsreportable.finra.org/OATSReportableSecurities-SOD.txt"
    searched_symbols = {}

    def __init__(self, IEX_TOKEN: str):
        self.IEX_TOKEN = IEX_TOKEN
        self.symbol_list, self.symbol_ts = self.get_symbol_list()

    def get_symbol_list(self):
        """
        Fetches a list of stock market symbols from FINRA
        
        Returns:
            pd.DataFrame -- [DataFrame with columns: Symbol | Issue_Name | Primary_Listing_Mkt
            datetime -- The time when the list of symbols was fetched. The Symbol list is updated every open and close of every trading day. 
        """
        raw_symbols = r.get(self.LIST_URL).text
        symbols = pd.DataFrame(
            [line.split("|") for line in raw_symbols.split("\n")][:-1]
        )
        symbols.columns = symbols.iloc[0]
        symbols = symbols.drop(symbols.index[0])
        symbols = symbols.drop(symbols.index[-1])
        symbols["Description"] = symbols["Symbol"] + ": " + symbols["Issue_Name"]
        return symbols, datetime.now()

    def search_symbols(self, search: str):
        """
        Performs a fuzzy search to find stock symbols closest to a search term.
        
        Arguments:
            search {str} -- String used to search, could be a company name or something close to the companies stock ticker.
        
        Returns:
            List of Tuples -- A list tuples of every stock sorted in order of how well they match. Each tuple contains: (Symbol, Issue Name).
        """
        try:  # https://stackoverflow.com/a/3845776/8774114
            return self.searched_symbols[search]
        except KeyError:
            pass
        if self.symbol_ts - datetime.now() > timedelta(hours=3):
            self.symbol_list, self.symbol_ts = self.get_symbol_list()

        symbols = self.symbol_list
        symbols["Match"] = symbols.apply(
            lambda x: fuzz.ratio(search.lower(), f"{x['Symbol']}".lower()), axis=1,
        )

        symbols.sort_values(by="Match", ascending=False, inplace=True)
        if symbols["Match"].head().sum() < 300:
            symbols["Match"] = symbols.apply(
                lambda x: fuzz.partial_ratio(search.lower(), x["Issue_Name"].lower()),
                axis=1,
            )

            symbols.sort_values(by="Match", ascending=False, inplace=True)
        symbols = symbols.head(10)
        symbol_list = list(zip(list(symbols["Symbol"]), list(symbols["Description"])))
        self.searched_symbols[search] = symbol_list
        return symbol_list

    def find_symbols(self, text: str):
        """
        Finds stock tickers starting with a dollar sign in a blob of text and returns them in a list. Only returns each match once. Example: Whats the price of $tsla? -> ['tsla']
        
        Arguments:
            text {str} -- Blob of text that might contain tickers with the format: $TICKER
        
        Returns:
            list -- List of every found match without the dollar sign. 
        """

        return list(set(re.findall(self.SYMBOL_REGEX, text)))

    def price_reply(self, symbols: list):
        """
        Takes a list of symbols and replies with Markdown formatted text about the symbols price change for the day.
        
        Arguments:
            symbols {list} -- List of stock market symbols.
        
        Returns:
            dict -- Dictionary with keys of symbols and values of markdown formatted text example: {'tsla': 'The current stock price of Tesla Motors is $**420$$, the stock price is currently **up 42%**}
        """
        dataMessages = {}
        for symbol in symbols:
            IEXurl = f"https://cloud.iexapis.com/stable/stock/{symbol}/quote?token={self.IEX_TOKEN}"

            response = r.get(IEXurl)
            if response.status_code == 200:
                IEXData = response.json()
                message = f"The current stock price of {IEXData['companyName']} is $**{IEXData['latestPrice']}**"
                # Determine wording of change text
                change = round(IEXData["changePercent"] * 100, 2)
                if change > 0:
                    message += f", the stock is currently **up {change}%**"
                elif change < 0:
                    message += f", the stock is currently **down {change}%**"
                else:
                    message += ", the stock hasn't shown any movement today."
            else:
                message = f"The symbol: {symbol} was not found."

            dataMessages[symbol] = message

        return dataMessages

    def dividend_reply(self, symbols: list):
        divMessages = {}

        for symbol in symbols:
            IEXurl = f"https://cloud.iexapis.com/stable/data-points/{symbol}/NEXTDIVIDENDDATE?token={self.IEX_TOKEN}"
            response = r.get(IEXurl)
            if response.status_code == 200:

                # extract date from json
                date = response.json()
                # Pattern IEX uses for dividend date.
                pattern = "%Y-%m-%d"
                divDate = datetime.strptime(date, pattern)

                daysDelta = (divDate - datetime.now()).days
                datePretty = divDate.strftime("%A, %B %w")
                if daysDelta < 0:
                    divMessages[
                        symbol
                    ] = f"{symbol.upper()} dividend was on {datePretty} and a new date hasn't been announced yet."
                elif daysDelta > 0:
                    divMessages[
                        symbol
                    ] = f"{symbol.upper()} dividend is on {datePretty} which is in {daysDelta} Days."
                else:
                    divMessages[symbol] = f"{symbol.upper()} is today."

            else:
                divMessages[
                    symbol
                ] = f"{symbol} either doesn't exist or pays no dividend."

        return divMessages

    def news_reply(self, symbols: list):
        newsMessages = {}

        for symbol in symbols:
            IEXurl = f"https://cloud.iexapis.com/stable/stock/{symbol}/news/last/3?token={self.IEX_TOKEN}"
            response = r.get(IEXurl)
            if response.status_code == 200:
                data = response.json()
                newsMessages[symbol] = f"News for **{symbol.upper()}**:\n"
                for news in data:
                    message = f"\t[{news['headline']}]({news['url']})\n\n"
                    newsMessages[symbol] = newsMessages[symbol] + message
            else:
                newsMessages[
                    symbol
                ] = f"No news found for: {symbol}\nEither today is boring or the symbol does not exist."

        return newsMessages

    def info_reply(self, symbols: list):
        infoMessages = {}

        for symbol in symbols:
            IEXurl = f"https://cloud.iexapis.com/stable/stock/{symbol}/company?token={self.IEX_TOKEN}"
            response = r.get(IEXurl)

            if response.status_code == 200:
                data = response.json()
                infoMessages[
                    symbol
                ] = f"Company Name: [{data['companyName']}]({data['website']})\nIndustry: {data['industry']}\nSector: {data['sector']}\nCEO: {data['CEO']}\nDescription: {data['description']}\n"

            else:
                infoMessages[
                    symbol
                ] = f"No information found for: {symbol}\nEither today is boring or the symbol does not exist."

        return infoMessages
