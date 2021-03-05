import pandas as pd
import numpy as np
from scipy import stats
import alpaca_trade_api as tradeapi
from pypfopt.efficient_frontier import EfficientFrontier
from pypfopt import risk_models
from pypfopt import expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices

# load data
df = pd.read_csv(r'<YOUR PATH>\back_data.csv')

# Your Alpaca API key_id and secret key 
key_id = 'key_id'
secret_key = 'secret_key'

# Initialize the alpaca api
base_url = "https://paper-api.alpaca.markets"

api = tradeapi.REST(
    key_id,
    secret_key,
    base_url,
    'v2'
    )

# Get the current positions from alpaca and create a df
positions = api.list_positions()

symbol, qty, market_value = [], [], []

for each in positions:
    symbol.append(each.symbol)
    qty.append(int(each.qty))
    market_value.append(float(each.market_value))

df_pf = pd.DataFrame(
    {
        'symbol': symbol,
         'qty': qty,
        'market_value': market_value
    }
)

# Current portfolio value
portfolio_value = round(df_pf['market_value'].sum(), 2)

# Select only symbol, close, date columns from df
df = df[['symbol', 'close', 'date']]

# Convert the date column to datetime
df['date'] = pd.to_datetime(df['date'])

# Sort by date (ascending) for the momentum calculation
df = df.sort_values(by='date').reset_index(drop=True)

# Get the latest date for the data we have
current_data_date = df['date'].max()

momentum_window = 125
minimum_momentum = 40

# Momentum score function
def momentum_score(ts):
    x = np.arange(len(ts))
    log_ts = np.log(ts)
    regress = scipy.stats.linregress(x, log_ts)
    annualized_slope = (np.power(np.exp(regress[0]), 252) -1) * 100
    return annualized_slope * (regress[2] ** 2)

df['momentum'] = df.groupby('symbol')['close'].rolling(
    momentum_window,
    min_periods=minimum_momentum
    ).apply(momentum_score).reset_index(level=0, drop=True)

# Get the top momentum stocks for the period
# Set the portfolio size we want
portfolio_size = 10


# Function to get the momentum stocks we want
def get_momentum_stocks(df, date, portfolio_size, cash):
    # Filter the df to get the top 10 momentum stocks for the latest day
    df_top_m = df.loc[df['date'] == pd.to_datetime(date)]
    df_top_m = df_top_m.sort_values(by='momentum', ascending=False).head(portfolio_size)

    # Set the universe to the top momentum stocks for the period
    universe = df_top_m['symbol'].tolist()

    # Create a df with just the stocks from the universe
    df_u = df.loc[df['symbol'].isin(universe)]

    # Create the portfolio
    # Pivot to format for the optimization library
    df_u = df_u.pivot_table(
        index='date', 
        columns='symbol',
        values='close',
        aggfunc='sum'
        )

    # Calculate expected returns and sample covariance
    mu = expected_returns.mean_historical_return(df_u)
    S = risk_models.sample_cov(df_u)

    # Optimise the portfolio for maximal Sharpe ratio
    ef = EfficientFrontier(mu, S) # Use regularization (gamma=1)
    weights = ef.max_sharpe()
    cleaned_weights = ef.clean_weights()

    # Allocate
    latest_prices = get_latest_prices(df_u)

    da = DiscreteAllocation(
        cleaned_weights,
        latest_prices,
        total_portfolio_value=cash
        )

    allocation = da.lp_portfolio(solver = 'ECOS_BB')[0]

    # Put the stocks and the number of shares from the portfolio into a df
    symbol_list = []
    num_shares_list = []

    for symbol, num_shares in allocation.items():
        symbol_list.append(symbol)
        num_shares_list.append(num_shares)

    # Now that we have the stocks we want to buy we filter the df for those ones
    df_buy = df.loc[df['symbol'].isin(symbol_list)]

    # Filter for the period to get the closing price
    df_buy = df_buy.loc[df_buy['date'] == date].sort_values(by='symbol')

    # Add in the qty that was allocated to each stock
    df_buy['qty'] = num_shares_list

    # Calculate the amount we own for each stock
    df_buy['amount_held'] = df_buy['close'] * df_buy['qty']
    df_buy = df_buy.loc[df_buy['qty'] != 0]
    return df_buy

# Call the function
df_buy = get_momentum_stocks(
        df=df,
        date=current_data_date,
        portfolio_size=portfolio_size,
        cash=portfolio_value
    )

# Figure out which stocks we need to sell
# Create a list of stocks to sell based on what is currently in our pf

sell_list = list(set(df_pf['symbol'].tolist()) - set(df_buy['symbol'].tolist()))

def sell_stocks(df, df_pf, sell_list, date):
    # Get the current prices and the number of shares to sell
    df_sell_price = df.loc[df['date'] == pd.to_datetime(date)]

    # Filter 
    df_sell_price = df_sell_price.loc[df_sell_price['symbol'].isin(sell_list)]

    # Check to see if there are any stocks in the current ones to buy
    # that are not in the current portfolio. It's possible there may not be any
    if df_sell_price.shape[0] > 0:
        df_sell_price = df_sell_price[[
            'symbol',
            'close'
        ]]

        # Merge with the current pf to get the number of shares we bought initially
        # so we know how many to sell
        df_buy_shares = df_pf[[
            'symbol',
            'qty'
        ]]

        df_sell = pd.merge(
            df_sell_price,
            df_buy_shares,
            on='symbol',
            how='left'
        )

    else:
        df_sell = None

    return df_sell

# Call the function
df_sell = sell_stocks(
    df=df,
    df_pf=df_pf,
    sell_list=sell_list,
    date=current_data_date
)

# Get a list of all stocks to sell i.e. any not in the current df_buy and any diff in qty
def stock_diffs(df_sell, df_pf, df_buy):
    df_stocks_held_prev = df_pf[['symbol', 'qty']]
    df_stocks_held_curr = df_buy[['symbol', 'qty', 'close']]

    # Inner merge to get the stocks that are the same week to week
    df_stock_diff = pd.merge(
        df_stocks_held_curr,
        df_stocks_held_prev,
        on='symbol',
        how='inner'
    )

    # Check to make sure not all of the stocks are different compared to what we have in the pf
    if df_stock_diff.shape[0] > 0:
        # Calculate any difference in positions based on the new pf
        df_stock_diff['share_amt_change'] = df_stock_diff['qty_x'] - df_stock_diff['qty_y']

        # Create df with the share difference and current closing price
        df_stock_diff = df_stock_diff[[
            'symbol',
            'share_amt_change',
            'close'
            ]]

        # If there's less shares compared to last week for the stocks that
        # are still in our portfolio, sell those shares
        df_stock_diff_sale = df_stock_diff.loc[df_stock_diff['share_amt_change'] < 0]

        # If there are stocks whose qty decreased,
        # add the df with the stocks that dropped out of the pf
        if df_stock_diff_sale.shape[0] > 0:
            if df_sell is not None:
                df_sell_final = pd.concat([df_sell, df_stock_diff_sale], sort=True)
                # Fill in NaNs in the share amount change column with
                # the qty of the stocks no longer in the pf, then drop the qty columns
                df_sell_final['share_amt_change'] = df_sell_final['share_amt_change'].fillna(df_sell_final['qty'])
                df_sell_final = df_sell_final.drop(['qty'], 1)
                # Turn the negative numbers into positive for the order
                df_sell_final['share_amt_change'] = np.abs(df_sell_final['share_amt_change'])
                df_sell_final.columns = df_sell_final.columns.str.replace('share_amt_change', 'qty')
            else:
                df_sell_final = df_stock_diff_sale
                # Turn the negative numbers into positive for the order
                df_sell_final['share_amt_change'] = np.abs(df_sell_final['share_amt_change'])
                df_sell_final.columns = df_sell_final.columns.str.replace('share_amt_change', 'qty')
        else:
            df_sell_final = None
    else:
        df_sell_final = df_stocks_held_prev      #modification curr --> prev

    return df_sell_final

# Call the function
df_sell_final = stock_diffs(
    df_sell=df_sell,
    df_pf=df_pf,
    df_buy=df_buy
)

# Send the sell order to the api
if df_sell_final is not None:
    symbol_list = df_sell_final['symbol'].tolist()
    qty_list = df_sell_final['qty'].tolist()
    try:
        for symbol, qty in list(zip(symbol_list, qty_list)):
            api.submit_order(
            symbol=symbol,
            qty=qty,
            side='sell',
            type='market',
            time_in_force='day'
            )
    except Exception:
        pass

# Buy the stocks that increased in shares compared
# to last week or any new stocks
def df_buy_new(df_pf, df_buy):
    # Left merge to get any new stocks or see if they changed qty
    df_buy_new = pd.merge(
        df_buy,
        df_pf,
        on='symbol',
        how='left'
        )

    # Get the qty we need to increase our positions by
    df_buy_new = df_buy_new.fillna(0)
    df_buy_new['qty_new'] = df_buy_new['qty_x'] - df_buy_new['qty_y']

    # Filter for only shares that increased
    df_buy_new = df_buy_new.loc[df_buy_new['qty_new'] > 0]
    if df_buy_new.shape[0] > 0:
        df_buy_new = df_buy_new[[
            'symbol',
            'qty_new'
        ]]
        df_buy_new = df_buy_new.rename(columns={'qty_new': 'qty'})
    else:
        df_buy_new = None

    return df_buy_new

# Call the function
df_buy_new = df_buy_new(
    df_pf=df_pf,
    df_buy=df_buy
)
# Send the buy order to the api
if df_buy_new is not None:
    symbol_list = df_buy_new['symbol'].tolist()
    qty_list = df_buy_new['qty'].tolist()
    try:
        for symbol, qty in list(zip(symbol_list, qty_list)):
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                type='market',
                time_in_force='day'
            )
    except Exception:
        pass