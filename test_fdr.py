import FinanceDataReader as fdr

codes = ['KRX:360750', '360750']

for code in codes:
    print(f"Testing code: {code}")
    try:
        df = fdr.DataReader(code)
        if df.empty:
            print(f"Result: Empty DataFrame")
        else:
            print(f"Result: Success, {len(df)} rows")
            print(df.tail(1))
    except Exception as e:
        print(f"Result: Error - {e}")
    print("-" * 20)
