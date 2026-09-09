"""
Data Utilities

Core dataframe helpers used across journalism analysis notebooks.
"""

import pandas as pd


def quick_info(df: pd.DataFrame) -> None:
    """
    Display quick information about a DataFrame.

    Args:
        df: pandas DataFrame
    """
    print("=" * 50)
    print("DATASET OVERVIEW")
    print("=" * 50)
    print(f"Shape: {df.shape}")
    print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    print("\nColumn Types:")
    print(df.dtypes.value_counts())

    print("\n" + "=" * 50)
    print("MISSING VALUES")
    print("=" * 50)
    missing = df.isnull().sum()
    missing_pct = 100 * missing / len(df)
    missing_table = pd.DataFrame({
        'Missing_Count': missing,
        'Missing_Percentage': missing_pct
    })
    missing_table = missing_table[missing_table['Missing_Count'] > 0]
    if len(missing_table) > 0:
        print(missing_table.sort_values('Missing_Count', ascending=False))
    else:
        print("No missing values found!")

    print("\n" + "=" * 50)
    print("BASIC STATISTICS")
    print("=" * 50)
    print(df.describe())


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean column names by removing special characters and spaces.

    Args:
        df: pandas DataFrame

    Returns:
        DataFrame with cleaned column names
    """
    df_cleaned = df.copy()
    df_cleaned.columns = (df_cleaned.columns
                         .str.strip()
                         .str.lower()
                         .str.replace(' ', '_')
                         .str.replace('[^a-zA-Z0-9_]', '', regex=True))
    return df_cleaned
