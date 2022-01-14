"""
多进程回测的流程: 
    Single_factor_test 实例化，读取eod_data_dict
    将eod_data_dict转为ndarray，传进multiprocessing的SharedMemory
    在每个进程中
        读取数据，转回eod_data_dict(目前默认values为DataFrame，后续优化为ndarray)
        Single_factor_test重新实例化，并运行run()函数完成回测
"""

# load packages 
import sys
import time
import logging
import traceback

import numpy as np
import pandas as pd
import multiprocessing as mp

sys.path.append("..")
logging.basicConfig(level=logging.CRITICAL)

# load files 
from configuration import config as cfg
from tools.datatools import DataAssist
from single_factor_test import SingleFactorBacktest
# from PqiDataSdk import *

sys.path.append('../..')
from data_ingestion.PqiDataSdk_Offline import PqiDataSdkOffline


class BasicBatchTest:
    def __init__(self):
        # self.myconnector = PqiDataSdk(user=cfg.user, size=20, pool_type="mp", log=False, offline=True)
        self.myconnector = PqiDataSdkOffline()
        self.start_date = cfg.start_date
        self.end_date = cfg.end_date
        self.stock_pool = self.myconnector.get_ticker_list()  # read all and mask later
        self.index_list = cfg.index_list
        pool_type = " + ".join(self.index_list) + ', ' + ('fmv weighted' if cfg.weight_index_by_fmv else 'equally weighted')
        self.pool_type = pool_type
        self.fix_stocks = cfg.fix_stocks
        self.fixed_stock_pool = cfg.fixed_stock_pool
        print(f'测试票池为: {self.pool_type}')
        self.usr = cfg.user
        self.max_processes = cfg.max_processes
        self.shape = []
        self.ind_shape = []
        self.factor_dict = {}
        self.key_list = []
        self.all_key_list = []
        self.namespace = ""
        self.name_list = []
        # 因子输入形式:{"function":函数,"ds_fac":ds上存储的因子, "ds_fund":ds上所有基本面数据}
        self.factor_path = cfg.factor_path


    def run(self, namespace="", name_list=None):
        self.namespace = namespace
        self.name_list = name_list
        self.load_data()
        self.read_factor()
        print("SHM ready")

    def load_data(self):
        # 读取数据
        tester = SingleFactorBacktest()
        eod_data_dict = tester.get_data()
        # 将数据转成ndarray，并存到SharedMemory
        df_sample = eod_data_dict["ClosePrice"]
        self.date_list = list(df_sample.columns)
        self.shape = df_sample.shape
        self.ind_shape = eod_data_dict["ind_df"].shape
        self.index_shape = eod_data_dict["index_data"].shape
        index_index_data_array = np.array(eod_data_dict["index_data"].index.T).astype("int")
        columns_index_data_array = np.array(eod_data_dict["index_data"].columns.T).astype("int")
        self.calendar_shape = eod_data_dict["calendar"].shape
        index_array = np.array(df_sample.index.T).astype("int")
        columns_array = np.array(df_sample.columns.T).astype("int")
        index_array_ind = np.array(eod_data_dict["ind_df"].index.T).astype("int")
        columns_array_ind = np.array(eod_data_dict["ind_df"].columns.T).astype("int")
        calendar = np.array(eod_data_dict["calendar"].astype("int"))
        abnormal_keys = []
        for k in eod_data_dict.keys():
            if k != "ind_df" and k != "calendar" and k != "index_data":
                if eod_data_dict[k].shape != self.shape:
                    print("delete {}  with shape {}".format(k, eod_data_dict[k].shape))
                    abnormal_keys.append(k)
        for k in abnormal_keys:
            del eod_data_dict[k]

        self.key_list = list(eod_data_dict.keys())
        self.all_key_list = self.key_list.copy()
        self.all_key_list.extend(["index", "columns", "index_ind", "columns_ind"])
        self.save_to_shm(index_array, "index")
        self.save_to_shm(columns_array, "columns")
        self.save_to_shm(index_array_ind, "index_ind")
        self.save_to_shm(columns_array_ind, "columns_ind")
        self.save_to_shm(calendar,"calendar")
        
        self.all_key_list.extend(["index_index_data", "columns_index_data"])
        self.save_to_shm(index_index_data_array, "index_index_data")
        self.save_to_shm(columns_index_data_array, "columns_index_data")

        for k in self.key_list:
            if k != 'calendar':
                data = eod_data_dict[k].values
                self.save_to_shm(data, k)


    def read_factor(self):
        """ 
        read all factors, pack into a dict of dataframes
        """

        # if self.fac_type == "ds_fund":
        #     self.factor_dict = self.myconnector.get_eod_history(tickers=self.stock_pool,
        #                                                         start_date=self.start_date,
        #                                                         end_date=self.end_date,
        #                                                         source="fundamental")
        # elif self.fac_type == "ds_fac":
        #     self.factor_dict = self.read_factor_data(self.name_list,self.stock_pool,self.date_list)
        # else:
        #     print("Factor input type must be defined")
        #     raise NotImplementedError
        self.factor_dict = self.read_factor_data(self.name_list, self.stock_pool, self.date_list)

        # add_list = []
        # current_trade_date = self.end_date
        #
        # for i in range(3):
        #     next_trade_date = self.myconnector.get_next_trade_date(trade_date = current_trade_date)
        #     if next_trade_date is None:
        #         break
        #     else:
        #         current_trade_date = next_trade_date
        #         add_list.append(next_trade_date)
        #
        # for i in range(len(self.factor_dict.keys())):
        #     factor_name = list(self.factor_dict.keys())[i]
        #     factor_df = self.factor_dict[factor_name]
        #     factor_df = factor_df.groupby(lambda x: x, axis=1).last()
        #     for d in add_list:
        #         factor_df[d] = [np.nan] * factor_df.shape[0]
        #     self.factor_dict[factor_name] = factor_df

    # TODO: edited here
    def read_factor_data(self, test_factor_list, tickers, date_list):
        """ 
        read factors and mask
        """
        # read index mask 
        index_mask = DataAssist.get_index_mask(self.index_list)

        # read raw factor dataframe
        feature_name_list = ["eod_" + feature_name for feature_name in test_factor_list]
        factor_dict = {}
        for factor_name in test_factor_list:
            factor_df = self.myconnector.read_eod_feature(factor_name)

            # dynamic stock pool (change stock pool as the index member stocks changes)
            if not self.fix_stocks:
                factor_dict[factor_name] = factor_df * index_mask
            # fixed stock pool
            else:
                factor_dict[factor_name] = factor_df + (factor_df.loc[self.fixed_stock_pool] - factor_df.loc[self.fixed_stock_pool])

            factor_dict[factor_name] = factor_df
        
        # # 将掩码覆盖到原因子值上
        # for factor in feature_name_list:
        #     raw_factor_df = factors[factor].to_dataframe()
        #     # 动态票池
        #     if not self.fix_stocks:
        #         factor_dict[factor[4:]] = raw_factor_df * index_mask
        #     # 静态票池
        #     else:
        #         factor_dict[factor[4:]] = raw_factor_df + (raw_factor_df.loc[self.fixed_stock_pool] - raw_factor_df.loc[self.fixed_stock_pool])

        return factor_dict


    def save_to_shm(self, data_nd, name):
        """
        读取ndarray和数据名称，存到SharedMemory
        :param data_nd:
        :param name:
        :return:
        """
        name = name + "," + self.usr
        shm_address = mp.shared_memory.SharedMemory(name=name, create=True, size=data_nd.nbytes)
        shm_nd_data = np.ndarray(data_nd.shape, dtype=data_nd.dtype, buffer=shm_address.buf)
        shm_nd_data[:] = data_nd[:]

    def shmClean(self):
        # 清理SharedMemory的内存占用
        for k in self.all_key_list:
            try:
                shm = mp.shared_memory.SharedMemory(name=k + "," + self.usr)
                shm.close()
                shm.unlink()
            except Exception as e:
                print(e)

# 子进程运行函数，避免作为成员函数定义
def processor(from_ds, factor, shape, ind_shape, index_shape, calendar_shape, usr, key_list):
    """
    单个因子的回测程序
    :param factor:
    :param from_ds:
    :param key_list:
    :param usr:
    :param ind_shape:
    :param index_shape:
    :param shape:
    :return:
    """
    # 重构data_dict
    data_dict = dict()
    try:
        shm_index = mp.shared_memory.SharedMemory(name='index' + "," + usr)
        index = np.ndarray((shape[0],), dtype='int', buffer=shm_index.buf)
        index = [str(x).zfill(6) for x in index]
        shm_columns = mp.shared_memory.SharedMemory(name='columns' + "," + usr)
        columns = np.ndarray((shape[1],), dtype='int', buffer=shm_columns.buf)
        columns = [str(x) for x in columns]

        shm_index_ind = mp.shared_memory.SharedMemory(name='index_ind' + "," + usr)
        index_ind = np.ndarray((ind_shape[0],), dtype='int', buffer=shm_index_ind.buf)
        index_ind = [str(x).zfill(6) for x in index_ind]
        shm_columns_ind = mp.shared_memory.SharedMemory(name='columns_ind' + "," + usr)
        columns_ind = np.ndarray((ind_shape[1],), dtype='int', buffer=shm_columns_ind.buf)
        columns_ind = [str(x).zfill(6) for x in columns_ind]

        shm_index_index_data = mp.shared_memory.SharedMemory(name='index_index_data' + "," + usr)
        index_index_data = np.ndarray((index_shape[0],), dtype='int', buffer=shm_index_index_data.buf)
        index_index_data = [str(x) for x in index_index_data]
        shm_columns_index_data = mp.shared_memory.SharedMemory(name='columns_index_data' + "," + usr)
        columns_index_data = np.ndarray((index_shape[1],), dtype='int', buffer=shm_columns_index_data.buf)
        columns_index_data = [str(x) for x in columns_index_data]

        for key in key_list:
            key = key + "," + usr
            # 行业dataframe
            if key == "ind_df" + "," + usr:
                shm_temp = mp.shared_memory.SharedMemory(name=key)
                data_temp = np.ndarray(ind_shape, dtype='float64', buffer=shm_temp.buf).copy()
                key = key.split(",")[0]
                data_dict[key] = pd.DataFrame(data=data_temp, index=index_ind, columns=columns_ind)

            # 指数收益序列dataframe
            elif key == "index_data" + "," + usr:
                shm_temp = mp.shared_memory.SharedMemory(name=key)
                data_temp = np.ndarray(index_shape, dtype='float64', buffer=shm_temp.buf).copy()
                key = key.split(",")[0]
                data_dict[key] = pd.DataFrame(data=data_temp, index=index_index_data, columns=columns_index_data)
            
            # 日期序列dataframe
            elif key == "calendar" + "," + usr:
                shm_temp = mp.shared_memory.SharedMemory(name=key)
                data_temp = np.ndarray(calendar_shape, dtype='float64', buffer=shm_temp.buf).copy()
                key = key.split(",")[0]
                data_dict[key] = data_temp

            # eod_data_dict中的其余字段
            else:
                shm_temp = mp.shared_memory.SharedMemory(name=key)
                data_temp = np.ndarray(shape, dtype='float64', buffer=shm_temp.buf).copy()
                key = key.split(",")[0]
                data_dict[key] = pd.DataFrame(data=data_temp, index=index, columns=columns)

    except Exception as e:
        error_message = "因子{}共享内存设置失败,失败原因: {}".format(factor[1], e) 
        print(error_message)
        error_message_complete = error_message + '\n' +  traceback.format_exc()
        return error_message_complete

    # 因子回测
    try:
        backtester = SingleFactorBacktest(offline=True) # daemonic processes are not allowed to have children
        backtester.get_data_multi(data_dict)
        if from_ds:
            return (backtester.run_ds_factor(factor[0], factor[1]))
        else:
            return (backtester.run(factor, data_dict))

    except Exception as e:
        error_message = "因子{}回测失败,失败原因: {}".format(factor[1], e)
        print(error_message)
        error_message_complete = error_message + '\n' +  traceback.format_exc()
        return error_message_complete

def save_record(summary_df):
    d = cfg.output_path
    curr_date = time.strftime('%Y%m%d', time.localtime(time.time()))
    # 创建当日文件夹
    save_path = '{}/facTest_file_{}_{}'.format(d, curr_date,cfg.test_name)
    summary_file = '{}/summary.csv'.format(save_path)
    try:
        final_summary_df = pd.read_csv(summary_file)
        del final_summary_df['Unnamed: 0']
        final_summary_df = pd.concat([final_summary_df,summary_df])
        final_summary_df.to_csv(summary_file)
    except FileNotFoundError:
        summary_df.to_csv(summary_file)


if __name__ == '__main__':

    factor_name_list = cfg.factor_name_list
    res_list = []
    batch_tester = BasicBatchTest()
    try: 
        batch_tester.run(namespace="", name_list=factor_name_list)

        # 定义进程池
        pool = mp.Pool(processes=cfg.max_processes)
        for i in range(len(batch_tester.factor_dict.keys())):
            factor_name = list(batch_tester.factor_dict.keys())[i]
            factor_df = batch_tester.factor_dict[factor_name]
            res_list.append(
                pool.apply_async(
                    processor, args=(
                        True, 
                        [factor_df, factor_name], 
                        batch_tester.shape,
                        batch_tester.ind_shape, 
                        batch_tester.index_shape, 
                        batch_tester.calendar_shape, 
                        batch_tester.usr, 
                        batch_tester.key_list,
            )))

        time.sleep(1)

        res_group_list = []
        for res in res_list:
            res_group_list.append(res.get())

        pool.close()
        pool.join()

        final_res_group_list = []
        for res in res_group_list:
            if res:
                # 如果运行失败, 打印失败原因
                if 'Traceback' in res:
                    print(res)
                # 如果运行成功, 加入最终报告
                elif len(res) == 51:
                    final_res_group_list.append(res)
        res_group_list = final_res_group_list

        # 记录因子
        summary_df = pd.DataFrame(np.array(res_group_list), columns=cfg.summary_cols)
        save_record(summary_df)
    except Exception as e: 
        print(e)
        print(traceback.format_exc())
    finally:
        # 清理共享内存
        batch_tester.shmClean()
