import string
import requests
import BeautifulSoup
import pickle

alpha = list(string.ascii_uppercase)

symbols = []

# Loop through the letters in the alphabet to get the stocks on each page
# from the table and store them in a list
for each in alpha:
    url = 'http://eoddata.com/stocklist/NYSE/{}.htm'.format(each)
    resp = requests.get(url)
    site = resp.content
    soup = BeautifulSoup(site, 'html.parser')
    table = soup.find('table', {'class': 'quotes'})
for row in table.findAll('tr')[1:]:
    symbols.append(row.findAll('td')[0].text.rstrip())       

# Remove the extra letters on the end
symbols_clean = []

for each in symbols:
    each = each.replace('.', '-')
    symbols_clean.append((each.split('-')[0]))

with open('/full/path/to/symbols.txt', 'wb') as f:
    pickle.dump(symbols_clean, f)      