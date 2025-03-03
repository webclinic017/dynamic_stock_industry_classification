""" 
Offline Version of PqiDataSdk, containing essential methods to support 
- factor generator
- backtest
- factor combination
- portfolio optimization
- graph clustering 
"""

# load packages 
import os
import pickle
import numpy as np
import pandas as pd 
from typing import List, Dict

# Specify paths 
RAW_PATH = 'data/raw'
PARSED_PATH = 'data/parsed'
FEATURE_PATH = 'data/features'

class PqiDataSdkOffline:

    def __init__(self) -> None:
        """
        get a copy of available trade dates and tickers 
        """
        self.get_all_trade_dates()
        self.get_all_tickers()

    def get_all_trade_dates(self):
        """ 
        get trade dates in this offline dateset 
        """
        # extract trade dates from file 
        trade_dates_path = os.path.join(PARSED_PATH, 'dates', 'dates.npy')
        with open(trade_dates_path, 'rb') as f:
            trade_dates = np.load(f, allow_pickle=True)
        
        # append to self 
        self.trade_dates = trade_dates
    
    def get_all_tickers(self):
        """
        get available tickers to trade (the cross-sectional snapshot at 20211231)
        """
        # extract tickers 
        tickers_path = os.path.join(PARSED_PATH, 'tickers', 'tickers.npy')
        with open(tickers_path, 'rb') as f:
            tickers = np.load(f, allow_pickle=True)
        
        # append to self
        self.tickers = tickers

    # ===================================
    # ---------- auxiliary --------------
    # ===================================
    def select_trade_dates(self, start_date: str, end_date: str) -> np.array:
        """ select a portion of trade dates """
        start_idx = np.where(self.trade_dates >= start_date)[0][0]
        end_idx = np.where(self.trade_dates <= end_date)[0][-1] + 1
        selected_trade_dates = self.trade_dates[start_idx:end_idx]
        return selected_trade_dates

    def get_next_trade_date(self, date: str) -> str:
        """ get next trade date (if empty output '') """
        cur_idx = np.where(self.trade_dates <= date)[0][-1]
        if cur_idx < len(self.trade_dates) - 1:
            next_day = self.trade_dates[cur_idx + 1]
        else:
            next_day = ''
        return next_day

    def get_prev_trade_date(self, date: str) -> str:
        """ get previous trade dates """
        cur_idx = np.where(self.trade_dates >= date)[0][0] 
        if cur_idx > 0: 
            prev_day = self.trade_dates[cur_idx - 1]
        else:
            prev_day = ''
        return prev_day

    def get_ticker_list(self):
        """ 
        get all stock code on A-share 
        """
        return self.tickers

    # ===================================
    # ---------- EOD History ------------
    # ===================================

    def get_ticker_list_date(self) -> Dict[str, str]:
        """
        get the list date of tickers
        :return the list date of each stock 
        """
        list_date_path = os.path.join(PARSED_PATH, 'stock_basics', 'ListDate')
        ser = pd.read_feather(list_date_path).set_index('ticker').squeeze()
        list_date_dict = ser.to_dict()
        return list_date_dict
        

    def get_sw_members(self) -> pd.DataFrame:
        """
        return sw level 1 industry classification（申万一级行业分类）
        """
        sw_path = os.path.join(PARSED_PATH, 'industry_class', 'SWClass')
        df = pd.read_feather(sw_path).rename(columns={'ticker': 'con_code', 'class_code': 'index_code'})
        return df

    @staticmethod
    def get_ticker_name_cn() -> Dict[str, str]:
        """
        get the chinese name of the tickers. If chinese name not available, use stock code 
        :return a dictionary, with stock code as key and stock name as value
        """
        stock_name_path = os.path.join(PARSED_PATH, 'tickers', 'ticker_name_cn_dict')
        with open(stock_name_path, 'rb') as f:
            ticker_name_cn_dict = pickle.load(f)
        return ticker_name_cn_dict

    def get_eod_history(
            self,
            tickers: List[str]=[],
            start_date: str='20160101',
            end_date: str='20180101',
            fields: List[str]=[],
            source: str='stock'
        ) -> Dict[str, pd.DataFrame]:
        """ 
        get eod_data_dict 

        :param tickers: the tickers to trade. If empty, read all 
        :param start_date, end_date: the start and end_date of the feature 
        :param fields: the fields to read. If empty, read all.
        :param source: the source of eod to read. Supporting 'stock', 'fund', and 'index'
        :return a dictionary of pd.DataFrame
        """
        eod_data_dict = {}

        # specify path to read 
        eod_data_path = os.path.join(PARSED_PATH, f'{source}_eod_data')

        # specify fields to read 
        if len(fields) == 0:
            fields = os.listdir(eod_data_path)

        # specify tickers to return 
        if len(tickers) == 0:
            tickers = self.tickers

        # select dates
        selected_trade_dates = self.select_trade_dates(start_date, end_date)
        columns_to_read = np.insert(selected_trade_dates, 0, 'index').tolist()

        # retrieve data
        for field in fields:
            feature_df_path = os.path.join(eod_data_path, field)
            feature_df = pd.read_feather(feature_df_path, columns=columns_to_read).set_index('index')
            eod_data_dict[field] = feature_df.loc[tickers]
        
        return eod_data_dict

    
    # ===================================
    # -------- EOD Feature IO -----------
    # ===================================

    def eod_feature_path_encoder(self, feature_name: str, des: str) -> str:
        """ 
        unified feature read/write path encoder 
        """
        feature_path = os.path.join(FEATURE_PATH, des, f'eod_{feature_name}')
        return feature_path

    def read_eod_feature(
            self, 
            feature_name: str, 
            des: str='factor', 
            dates: List[str]=[]
        ) -> pd.DataFrame:
        """
        read feature by name 

        :param feature_name: the name fo the feature 
        :param des: the destination to retrieve factor. Supporting 'factor', 'support_factor', 'risk_factor', 'ml_factor'
        :param dates: the dates of the list. If empty, read all dates available
        :return a feature dataframe 
        """
        feature_path = self.eod_feature_path_encoder(feature_name, des)

        # specify columns 
        columns_to_read = dates 
        if len(columns_to_read) == 0:
            columns_to_read = self.trade_dates
        columns_to_read = np.insert(columns_to_read, 0, 'index').tolist()

        # retrieve 
        feature_df = pd.read_feather(feature_path, columns=columns_to_read).set_index('index')
        return feature_df


    # TODO: how to avoid covering the original ones? 
    def save_eod_feature(self, feature_name: str, feature_df: pd.DataFrame, des: str='factor') -> None:
        """ 
        save computed features. All named f'eod_{feature_name}'
        
        :param feature_name: the name of the feature 
        :param feature_df: dataframe
        :param des: the destination of the path. Supporting 'factor', 'support_factor', 'risk_factor', 'ml_factor'
        """
        feature_path = os.path.join(FEATURE_PATH, des, f'eod_{feature_name}')
        feature_df.reset_index().to_feather(feature_path)

    # ===================================
    # -------- Index Mask ---------------
    # ===================================

    # TODO: change corresponding parts in backtest and factor comb
    def get_stock_weight(
            self,
            index: str,
            trade_dates: List[str] = None
        ) -> pd.DataFrame:
        """
        get stock weights of an given index within a timeframe 
        :param index
        :param list of trade dates
        :return: a dataframe, stock codes as index, dates as columns, and stock weights as values
        """
        # convert name to code 
        index_to_weight = {
            'zz500': '000905',
            'zz1000': '000852',
            'zzall': '000985',
            'sz50': '000016',
            'hs300': '000300'
        }
        # specify path 
        index_path = os.path.join(PARSED_PATH, 'index_stock_weight', index_to_weight[index])
        # retrieve 
        index_data = pd.read_feather(index_path).set_index("index")

        # select trade dates 
        if trade_dates is None:
            trade_dates = self.trade_dates  # all dates
        df_selected = index_data.loc[:, trade_dates]
        return df_selected

    def get_index_mask(
            self,
            index_list: List[str]
        ):
        """
        retrieve index member stock info, 1 if is a member, and nan otherwise
        :param index_list: a list of stock index codes 
        :return a nan mask
        """
        agg_index_mask = False
        # read and combine different masks
        for index in index_list:
            index_weight = self.get_stock_weight(index)
            index_mask = index_weight.notna()
            agg_index_mask = agg_index_mask | index_mask
        # convert to 1 and nans
        agg_index_mask = agg_index_mask.astype(int) / agg_index_mask.astype(int)
        return agg_index_mask       

    # ==========================================
    # -------- Dynamic Industyr IO -------------
    # ==========================================

    def ind_feature_path_encoder(self, ind_name: str, des: str) -> str:
        """ 
        unified feature read/write path encoder 
        """
        feature_path = os.path.join(FEATURE_PATH, des, f'ind_{ind_name}')
        return feature_path

    def read_ind_feature(
         self,
         ind_name: str,
         des: str = 'dynamic_ind',
         dates: List[str] = []
     ) -> pd.DataFrame:
        """
        read ind info by name 

        :param ind_name: the name fo the feature 
        :param des: the destination to retrieve factor. default to 'dynamic_ind'
        :param dates: the dates of the list. If empty, read all dates available
        :return a feature dataframe 
        """
        feature_path = self.ind_feature_path_encoder(ind_name, des)

        # specify columns
        columns_to_read = dates
        if len(columns_to_read) == 0:
            columns_to_read = self.trade_dates
        columns_to_read = np.insert(columns_to_read, 0, 'index').tolist()

        # retrieve
        ind_df = pd.read_feather(
            feature_path, columns=columns_to_read
        ).set_index('index').astype(int)
        return ind_df

    def save_ind_feature(self, ind_name: str, ind_df: pd.DataFrame, des: str='dynamic_ind') -> None:
        """ 
        save computed features. All named f'eod_{ind_name}'
        
        :param ind_name: the name of the feature 
        :param feature_df: dataframe
        :param des: the destination of the path. default to 'dynamic_ind'
        """
        feature_path = os.path.join(FEATURE_PATH, des, f'ind_{ind_name}')
        ind_df.astype(int).reset_index().to_feather(feature_path)
