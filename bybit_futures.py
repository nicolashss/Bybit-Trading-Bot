# -------------------------

# Author: Doom & Oji Wolf
# Github : https://github.com/nicolashss/TradingBOT
# Website : https://xlux.xyz/

# -------------------------

import os
import sys

from colorama import init, Fore, Back, Style
from pprint import pprint

from time import sleep, time

import pandas_ta as ta

import json
import math
import time

import telepot

import pandas as pd     # needs pip install
import numpy as np
import matplotlib.pyplot as plt   # needs pip install
from operator import add
from operator import sub

import ccxt
import calendar
from datetime import datetime

from tradingview_ta import TA_Handler, Interval, Exchange
import tradingview_ta

import yaml

#GLOBAL
Telegram_Start_Command_Triggered = False
Telegram_Pair = "None"
Telegram_TradeAmount = -1.0
Telegram_Leverage = -1
TelegramStopSignal = False
Telegram_LastTradeStop = False
telegram_bot = None
chat_id = None


#CALCULATION AND DATA FUNCTION

def get_data_frame(client, crypto, Interval):
    global telegram_bot
    # valid intervals - 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
    # request historical candle (or klines) data using timestamp from above, interval either every min, hr, day or month
    # starttime = '30 minutes ago UTC' for last 30 mins time
    # e.g. client.get_historical_klines(symbol='ETHUSDTUSDT', '1m', starttime)
    # starttime = '1 Dec, 2017', '1 Jan, 2018'  for last month of 2017
    # e.g. client.get_historical_klines(symbol='BTCUSDT', '1h', "1 Dec, 2017", "1 Jan, 2018")
    #starttime = StartTime  # to start for 1 day ago
    interval = Interval
    while True:
        try:
            #bars = client_binance.futures_historical_klines(crypto, interval, starttime)
            bars = client.fetch_ohlcv(symbol=crypto, timeframe=interval, limit=200)
            break
        except Exception as e:
            print(e)
            telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à récupérer les Bougies de Binance, si ça se reproduit trop de fois à la suite, veuillez me stopper.")
            pass
    #pprint.pprint(bars)
    
    df = pd.DataFrame(bars, columns = ['Time', 'open', 'high', 'low', 'close', 'volume'])
    df['Time'] = [datetime.fromtimestamp(float(time)/1000) for time in df['Time']]
    #df.set_index('Time', inplace=True)
    
    return df

def EMA(data, n=20):

    emas = data.ewm(span=n,adjust=False).mean()

    return emas

def SqueezeMomentum(df):

    # calculate Bollinger Bands
    # moving average
    length = 20
    mult = 2
    length_KC = 20
    mult_KC = 1.5
    m_avg = df['close'].rolling(window=length).mean()
    # standard deviation
    m_std = df['close'].rolling(window=length).std(ddof=0)
    # upper Bollinger Bands
    df['upper_BB'] = m_avg + mult * m_std
    # lower Bollinger Bands 
    df['lower_BB'] = m_avg - mult * m_std

    # calculate Keltner Channel
    # first we need to calculate True Range
    df['tr0'] = abs(df["high"] - df["low"])
    df['tr1'] = abs(df["high"] - df["close"].shift())
    df['tr2'] = abs(df["low"] - df["close"].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    # moving average of the TR
    range_ma = df['tr'].rolling(window=length_KC).mean()
    # upper Keltner Channel
    df['upper_KC'] = m_avg + range_ma * mult_KC
    # lower Keltner Channel
    df['lower_KC'] = m_avg - range_ma * mult_KC

    # check for 'squeeze'
    #df['squeeze_on'] = (df['lower_BB'] > df['lower_KC']) and (df['upper_BB'] < df['upper_KC'])
    #df['squeeze_off'] = (df['lower_BB'] < df['lower_KC']) and (df['upper_BB'] > df['upper_KC'])

    # calculate momentum value
    highest = df['high'].rolling(window = length_KC).max()
    lowest = df['low'].rolling(window = length_KC).min()
    m1 = (highest + lowest) / 2
    df['momentum_value'] = (df['close'] - (m1 + m_avg)/2)
    fit_y = np.array(range(0,length_KC))
    df['momentum_value'] = df['momentum_value'].rolling(window = length_KC).apply(lambda x : np.polyfit(fit_y, x, 1)[0] * (length_KC-1) + np.polyfit(fit_y, x, 1)[1], raw=True)

def psar(barsdata, iaf = 0.02, maxaf = 0.2):
    length = len(barsdata)
    #dates = list(barsdata['Time'])
    high = list(barsdata['high'])
    low = list(barsdata['low'])
    close = list(barsdata['close'])
    psar = close[0:len(close)]
    psarbull = [None] * length
    psarbear = [None] * length
    bull = True
    af = iaf
    ep = low[0]
    hp = high[0]
    lp = low[0]
    for i in range(2,length):
        if bull:
            psar[i] = psar[i - 1] + af * (hp - psar[i - 1])
        else:
            psar[i] = psar[i - 1] + af * (lp - psar[i - 1])
        reverse = False
        if bull:
            if low[i] < psar[i]:
                bull = False
                reverse = True
                psar[i] = hp
                lp = low[i]
                af = iaf
        else:
            if high[i] > psar[i]:
                bull = True
                reverse = True
                psar[i] = lp
                hp = high[i]
                af = iaf
        if not reverse:
            if bull:
                if high[i] > hp:
                    hp = high[i]
                    af = min(af + iaf, maxaf)
                if low[i - 1] < psar[i]:
                    psar[i] = low[i - 1]
                if low[i - 2] < psar[i]:
                    psar[i] = low[i - 2]
            else:
                if low[i] < lp:
                    lp = low[i]
                    af = min(af + iaf, maxaf)
                if high[i - 1] > psar[i]:
                    psar[i] = high[i - 1]
                if high[i - 2] > psar[i]:
                    psar[i] = high[i - 2]
        if bull:
            psarbull[i] = psar[i]
        else:
            psarbear[i] = psar[i]
    return {"high":high, "low":low, "close":close, "psar":psar, "psarbear":psarbear, "psarbull":psarbull}

def getUSDTBalanceSTR():
    global telegram_bot
    try:
        acc_balance = bybit.fetch_balance()['free']['USDT']
    except Exception as e:
        print(e)
        telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à récupérer le montant de ta balance USDT STR, peut-être un problème d'api, je m'arrête.")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)

    return str(acc_balance)

def getUSDTBalanceFLOAT():
    global telegram_bot
    try:
        acc_balance = bybit.fetch_balance()['free']['USDT']
    except Exception as e:
        print(e)
        telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à récupérer le montant de ta balance USDT FLOAT, peut-être un problème d'api, je m'arrête.")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)

    return acc_balance

#CALCULATION AN DATA FUNCTION END

def get_API():

    try:
        yaml_file = open("./api.yaml", 'r')
    except:
        print(Fore.RED + "[ERREUR] :")
        print(Fore.WHITE + "Le fichier api.yaml n'existe pas ou n'est pas au bon endroit")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
    
    

    yaml_content = yaml.safe_load(yaml_file)
    return yaml_content


def round_decimals_down(number:float, decimals:int=2):
    """
    Returns a value rounded down to a specific number of decimal places.
    """
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer")
    elif decimals < 0:
        raise ValueError("decimal places has to be 0 or more")
    elif decimals == 0:
        return math.floor(number)

    factor = 10 ** decimals
    return math.floor(number * factor) / factor

def handle_TELEGRAM_COMMAND(msg):
    
    global Telegram_Start_Command_Triggered
    global Telegram_Pair
    global Telegram_TradeAmount
    global Telegram_Leverage
    global TelegramStopSignal
    global Telegram_LastTradeStop
    global telegram_bot
    global chat_id

    chat_id = msg['chat']['id']
    command = msg['text']

    if command == 'command start':
        if Telegram_Pair == "None" :
            telegram_bot.sendMessage(chat_id, "[BOT] : Tu n'as pas rentré de pair, je ne peux pas démarrer")
        elif Telegram_TradeAmount == -1.0:
            telegram_bot.sendMessage(chat_id, "[BOT] : Tu n'as pas rentré de mise, je ne peux pas démarrer")
        elif Telegram_Leverage == -1:
            telegram_bot.sendMessage(chat_id, "[BOT] : Tu n'as pas rentré de multiplicateur, je ne peux pas démarrer")
        else :
            telegram_bot.sendMessage(chat_id, "[BOT] : Je démarre.")
            Telegram_Start_Command_Triggered = True

    elif command == 'command info':
        message = "[BOT] : La pair actuelle est : " + str(Telegram_Pair) + ". La mise actuelle est : " + str(Telegram_TradeAmount) + ". Le multiplicateur actuelle est : " + str(Telegram_Leverage) + "."
        telegram_bot.sendMessage(chat_id, message)
        #os.execv(sys.executable, [sys.executable, __file__] + sys.argv)

    elif command == 'command stop':
        telegram_bot.sendMessage(chat_id, "[BOT] : Je m'arrête. à plus dans le bus")
        #os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
        TelegramStopSignal = True

    elif command == 'command ping':
        telegram_bot.sendMessage(chat_id, "[BOT] : pong")

    elif command.find('command set_pair') != -1 :
        arguments = command[17:]
        Telegram_Pair = str(arguments)
        message = "[BOT] : La pair est mise à jour : " + str(Telegram_Pair)
        telegram_bot.sendMessage(chat_id, message)

    elif command.find('command set_trade_amount') != -1 :
        arguments = command[25:]
        Telegram_TradeAmount = float(arguments)
        message = "[BOT] : La mise est mise à jour : " + str(Telegram_TradeAmount)
        telegram_bot.sendMessage(chat_id, message)

    elif command.find('command set_leverage') != -1 :
        arguments = command[21:]
        Telegram_Leverage = int(arguments)
        message = "[BOT] : Le multiplicateur est mis à jour : " + str(Telegram_Leverage)
        telegram_bot.sendMessage(chat_id, message)

    elif command == 'command last_trade_stop':
        telegram_bot.sendMessage(chat_id, "[BOT] Ok, je m'arrête à la fin du trade :) (ou de suite si y a pas de trade en cours)")
        Telegram_LastTradeStop = True
    


if __name__ == "__main__":

    init()

    api_yaml = get_API()

    binance_api_is_here = False
    binance_secret_is_here = False
    binance_telegram_bot_token_is_here = False

    if "binance_api" in api_yaml:
        binance_api_is_here = True
    if "binance_secret" in api_yaml:
        binance_secret_is_here = True
    if "telegram_bot_token" in api_yaml:
        binance_telegram_bot_token_is_here = True

    if binance_api_is_here == False :
        print(Fore.RED + "[ERREUR] :")
        print(Fore.WHITE + "Il manque -binance_api- dans le fichier api.yaml")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
    if binance_secret_is_here == False :
        print(Fore.RED + "[ERREUR] :")
        print(Fore.WHITE + "Il manque -binance_secret- dans le fichier api.yaml")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
    if binance_telegram_bot_token_is_here == False :
        print(Fore.RED + "[ERREUR] :")
        print(Fore.WHITE + "Il manque -telegram_bot_token- dans le fichier api.yaml")
        os.execv(sys.executable, [sys.executable, __file__] + sys.argv)

    bybit = ccxt.bybit({
        'apiKey': api_yaml['binance_api'],
        'secret': api_yaml['binance_secret'],
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
        }
    })
    bybit.load_markets()
    telegram_bot = telepot.Bot(api_yaml['telegram_bot_token'])
    telegram_bot.message_loop(handle_TELEGRAM_COMMAND)
    
    print(Fore.RED + "[BOT] : ")
    print(Fore.YELLOW + "Commandes du BOT (a envoyer depuis Telegram) :")
    print(Fore.GREEN + "command start :")
    print(Fore.WHITE + "Lance le bot.")
    print(Fore.GREEN + "command info :")
    print(Fore.WHITE + "Donne les paramétrages actuelle du bot.")
    print(Fore.GREEN +"command stop : ")
    print(Fore.WHITE + "Stop le bot.")
    print(Fore.GREEN +"command last_trade_stop : ")
    print(Fore.WHITE + "Termine le dernier trade et arrête le bot,")
    print("si aucun trade n'est en cours, le bot se stop directement.")
    print(Fore.GREEN +"command set_pair -Pair- : ")
    print(Fore.WHITE + "Permet de choisir la pair, ")
    print("une fois que le bot est lancé, ce n'est plus modifiable. (exemple : command set_pair BTCUSDT)")
    print(Fore.GREEN +"command set_trade_amount -Amount- : ")
    print(Fore.WHITE + "Permet de choisir le montant de la mise,")
    print("une fois que le bot est lancé, ce n'est plus modifiable. (exemple : command set_trade_amount 50.5)")
    print(Fore.GREEN +"command set_leverage -Leverage- : ")
    print(Fore.WHITE + "Permet de choisir le multiplicateur de trade, prenez soin de le mettre avant de lancer le bot,")
    print("une fois que le bot est lancé, ce n'est plus modifiable, faite attention de mettre un multiplicateur accepté par votre compte.")
    print("(exemple : command set_leverage 10)")
    print(Fore.GREEN +"command ping : ")
    print(Fore.WHITE + "Si le bot tourne toujours, il renvoit un message 'pong'")

    print(Fore.YELLOW + "Veuillez parametrer la Pair et le montant de la mise depuis Telegram")
    print(Fore.YELLOW + "Puis vous pouver lancer le bot")

    while(Telegram_Start_Command_Triggered == False):
        i = 0

    #PARAMETER
    leverage = Telegram_Leverage
    pair = Telegram_Pair

    handler = TA_Handler(
        symbol=pair,
        exchange="BYBIT",
        screener="crypto",
        interval="5m",
        timeout=None
    )


    actualBalance = getUSDTBalanceSTR()
    print("Balance Amount in Futures :")
    print(actualBalance)
    message = "[BOT] : Voici ta balance : " + str(actualBalance) + " USDT"
    telegram_bot.sendMessage(chat_id, message)

    try:
        ret = bybit.set_margin_mode(symbol=pair, marginType='ISOLATED', params={'leverage':float(int(leverage))})

    except Exception as e:
        print(e)

    isLongTake = False
    isShortTake = False
    FirstPoint = False
    lastPricetrade = None
    TradeOrderTime = 0
    TradeOrderTimeSave = 0
    TradeCloseTime = 0
    LogPNL = False

    StopLossPrice = None
    TakeProfitPrice = None

    counterToNotice = 0

    quantityUSDTTrade = Telegram_TradeAmount
    pair = Telegram_Pair

    TradeDateTake = ' '
    TradeDateStop = ' '
    LastDate = ' '
    LastBalanceFloat = 0.0

    lastBullSAR = -1
    lastBearSAR = -1

    lastBullSARIndex = -1
    lastBearSARIndex = -1

    while True:

        DataCrypto = get_data_frame(bybit, pair, '5m')

        SqueezeMomentum(DataCrypto)
        SAR = psar(DataCrypto)
        EMA_100 = EMA(DataCrypto['close'], 100)

        colors = []
        for ind, val in enumerate(DataCrypto['momentum_value']):
            if ind > 0:
              if val >= 0:
                color = 'green'
                if val > DataCrypto['momentum_value'][ind-1]:
                  color = 'lime'
              else:
                color = 'maroon'
                if val < DataCrypto['momentum_value'][ind-1]:
                  color='red'
              colors.append(color)
            else:
              colors.append('grey')

        for z in range(len(DataCrypto['close'])):
            if z == len(DataCrypto['close'])-1:
                continue
            if SAR['psarbear'][z] != None:
                lastBearSAR = SAR['psarbear'][z]
                lastBearSARIndex = z
            if SAR['psarbull'][z] != None:
                lastBullSAR = SAR['psarbull'][z]
                lastBullSARIndex = z

        while True:
            try:
                analysis = handler.get_analysis()
                break
            except Exception as e:
                print(e)
                telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à récupérer les datas de l'indicateur TA.")
                pass


        srcCloseElement = len(DataCrypto['close'])-1

        if (isLongTake == True or isShortTake == True):
            symbol = pair
            market = bybit.market(symbol)

            response = bybit.private_linear_get_position_list({'symbol':market['id']})
            linear_positions = response['result']
            print(linear_positions[0]['size'])
            if linear_positions[0]['size'] == "0":
                isLongTake = False
                isShortTake = False
                LogPNL = True


        if TelegramStopSignal == True:
            os.execv(sys.executable, [sys.executable, __file__] + sys.argv)

        if LogPNL == True:
            Profit = getUSDTBalanceFLOAT() - LastBalanceFloat
            print("PNL : ")
            message = "[BOT] : Bop, un trade est terminé. Voici les gains = " + str(Profit) + " et voici ta Balance : " + str(getUSDTBalanceSTR())
            
            while True:
                try:
                    telegram_bot.sendMessage(chat_id, message)
                    break
                except Exception as e:
                    print(e)
                    pass
            if Telegram_LastTradeStop == True:
                
                while True:
                    try:
                        telegram_bot.sendMessage(chat_id, "[BOT] : Le trade est fini, je m'arrête ! ")
                        break
                    except Exception as e:
                        print(e)
                        pass
                os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
            LogPNL = False
            quantityUSDTTrade = Telegram_TradeAmount
            pair = Telegram_Pair

        if Telegram_LastTradeStop == True and isLongTake == False and isShortTake == False:
            while True:
                try:
                    telegram_bot.sendMessage(chat_id, "[BOT] : Pas de trade en cours, je m'arrête ! ")
                    break
                except Exception as e:
                    print(e)
                    pass
            
            os.execv(sys.executable, [sys.executable, __file__] + sys.argv)
                

        while True:
            try:
                pairPrice = float(bybit.fetchTicker(symbol=pair)['info']['last_price'])
                break
            except Exception as e:
                print(e)
                telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à récupérer le prix de la pair, si ça se reproduit trop de fois à la suite, veuillez me stopper.")
                pass


        quantityCryptoToBuy = quantityUSDTTrade * leverage / pairPrice
        
        if isLongTake == False and isShortTake == False:
            if (analysis.oscillators['RECOMMENDATION'] == 'NEUTRAL' or analysis.oscillators['RECOMMENDATION'] == 'BUY' or analysis.oscillators['RECOMMENDATION'] == 'STRONG_BUY') and analysis.moving_averages['RECOMMENDATION'] == 'STRONG_BUY' and lastBullSAR != -1 and lastBearSAR != -1 and SAR['psarbull'][srcCloseElement-1] != None and (SAR['psarbear'][srcCloseElement-2] != None or SAR['psarbear'][srcCloseElement-3] != None) and SAR['psarbull'][lastBearSARIndex+1] > EMA_100[srcCloseElement-1] and lastBearSAR > EMA_100[srcCloseElement-1] and DataCrypto['close'][srcCloseElement-1] > lastBearSAR and (colors[srcCloseElement-1] == 'maroon'):
                
                StopLossPrice = DataCrypto['low'][lastBearSARIndex]

                if float(DataCrypto['open'][srcCloseElement]) - ((float(DataCrypto['open'][srcCloseElement]) * 3.0)/100) <= float(DataCrypto['close'][lastBearSARIndex]) and StopLossPrice < DataCrypto['open'][srcCloseElement]:

                    #StopLossPrice = round_decimals_down(StopLossPrice, int(pricePrecision))
                    TakeProfitPrice =  DataCrypto['open'][srcCloseElement] + (((DataCrypto['low'][lastBearSARIndex] - DataCrypto['open'][srcCloseElement]) * 1.0) * -1.0)
                    LastBalanceFloat = getUSDTBalanceFLOAT()
                    #TakeProfitPrice = round_decimals_down(TakeProfitPrice, int(pricePrecision));
                    StopLossPrice = round_decimals_down(StopLossPrice, 4)
                    TakeProfitPrice = round_decimals_down(TakeProfitPrice, 4)
                    while True:
                        try:
                            bybit.create_order(pair, 'Market', 'buy', quantityCryptoToBuy, params={'take_profit': TakeProfitPrice, 'stop_loss': StopLossPrice})
                            break
                        except Exception as e:
                            print(e)
                            telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à prendre un LONG, si ça se reproduit plus de 3 fois à la suite, veuillez me stopper, et allez couper le trade à la main.")
                            pass
                    
                    #lastPricetrade = pairPrice
                    message = "[BOT] : J'ai pris un Trade Long. "
                    #TradeDateTake = DataCrypto['date'][srcCloseElement]
                    while True:
                        try:
                            telegram_bot.sendMessage(chat_id, message)
                            break
                        except Exception as e:
                            print(e)
                            pass
                    
                    #print(res)
                    
                    isLongTake = True
                
                
            elif (analysis.oscillators['RECOMMENDATION'] == 'NEUTRAL' or analysis.oscillators['RECOMMENDATION'] == 'SELL' or analysis.oscillators['RECOMMENDATION'] == 'STRONG_SELL') and analysis.moving_averages['RECOMMENDATION'] == 'STRONG_SELL' and lastBullSAR != -1 and lastBearSAR != -1 and SAR['psarbear'][srcCloseElement-1] != None and (SAR['psarbull'][srcCloseElement-2] != None or SAR['psarbull'][srcCloseElement-3] != None) and SAR['psarbear'][lastBullSARIndex+1] < EMA_100[srcCloseElement-1] and lastBullSAR < EMA_100[srcCloseElement-1] and DataCrypto['close'][srcCloseElement-1] < lastBullSAR and (colors[srcCloseElement-1] == 'green'):
                
                StopLossPrice = DataCrypto['high'][lastBullSARIndex]

                if float(DataCrypto['open'][srcCloseElement]) + ((float(DataCrypto['open'][srcCloseElement]) * 3.0)/100) >= float(DataCrypto['close'][lastBullSARIndex]) and StopLossPrice > DataCrypto['open'][srcCloseElement]:

                    #StopLossPrice = round_decimals_down(StopLossPrice, int(pricePrecision))
                    TakeProfitPrice =  DataCrypto['open'][i] - (((DataCrypto['high'][lastBullSARIndex] - DataCrypto['open'][i]) * 1.0))
                    LastBalanceFloat = getUSDTBalanceFLOAT()
                    StopLossPrice = round_decimals_down(StopLossPrice, 4)
                    TakeProfitPrice = round_decimals_down(TakeProfitPrice, 4)
                    #TakeProfitPrice = round_decimals_down(TakeProfitPrice, int(pricePrecision));
                    while True:
                        try:
                            bybit.create_order(pair, 'Market', 'sell', quantityCryptoToBuy, params={'take_profit': TakeProfitPrice, 'stop_loss': StopLossPrice})
                            #TradeOrderTime = res['updateTime']
                            break
                        except Exception as e:
                            print(e)
                            telegram_bot.sendMessage(chat_id, "[BOT] : Erreur : Je n'arrive pas à prendre un LONG, si ça se reproduit plus de 3 fois à la suite, veuillez me stopper, et allez couper le trade à la main.")
                            pass
                    
                    #lastPricetrade = pairPrice
                    message = "[BOT] : J'ai pris un Trade Short. "
                    #TradeDateTake = DataCrypto['date'][srcCloseElement]
                    while True:
                        try:
                            telegram_bot.sendMessage(chat_id, message)
                            break
                        except Exception as e:
                            print(e)
                            pass
                    
                    #print(res)
                    
                    isShortTake = True
                
        #LastDate = DataCrypto['date'][i]
        time.sleep(1)