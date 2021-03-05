import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

# Function to turn a datetime object into unix
def unix_time_millis(dt):
    epoch = datetime.utcfromtimestamp(0)
    return int((dt - epoch).total_seconds() * 1000.0)

# Get the historical dates you need.
today = datetime.today().astimezone(pytz.timezone("America/New_York"))
today_fmt = today.strftime('%Y-%m-%d')
today = datetime.strptime(today_fmt, '%Y-%m-%d')
date = datetime.strptime('2021-01-04', '%Y-%m-%d')

# Convert to unix for the API
today_ms = unix_time_millis(today)
date_ms = unix_time_millis(date)

# Get list of stock symbols
with open('/full/path/to/symbols.txt', 'rb') as f:
    symbols_clean = pickle.load(f)
    
# Get the price history for each stock
consumer_key = 'Your TD Ameritrade API key'

data_list = []

for each in symbols_clean:
    url = r"https://api.tdameritrade.com/v1/marketdata/{}/pricehistory".format(each)

    # You can do whatever period/frequency you want
    # This will grab the data for a single day
    params = {
        'apikey': consumer_key,
        'periodType': 'month',
        'frequencyType': 'daily',
        'frequency': '1',
        'startDate': date_ms,
        'endDate': date_ms,
        'needExtendedHoursData': 'true'
        }

    request = requests.get(
        url=url,
        params=params
        )

    data_list.append(request.json())
    time.sleep(.5)

# Create a list for each data point and loop through the json, adding the data to the lists
symbl_l, open_l, high_l, low_l, close_l, volume_l, date_l = [], [], [], [], [], [], []

for data in data_list:
    try:
        symbl_name = data['symbol']
    except KeyError:
        symbl_name = np.nan
    try:
        for each in data['candles']:
            symbl_l.append(symbl_name)
            open_l.append(each['open'])
            high_l.append(each['high'])
            low_l.append(each['low'])
            close_l.append(each['close'])
            volume_l.append(each['volume'])
            date_l.append(each['datetime'])
    except KeyError:
        pass

# Create a df from the lists
df = pd.DataFrame(
     {
        'symbol': symbl_l,
        'open': open_l,
        'high': high_l,
        'low': low_l,
        'close': close_l, 
        'volume': volume_l,
        'date': date_l
    }
 )

# Format the dates
df['date'] = pd.to_datetime(df['date'], unit='ms')
df['date'] = df['date'].dt.strftime('%Y-%m-%d')

# Save to csv
df.to_csv(r'<YOUR PATH>\back_data.csv')