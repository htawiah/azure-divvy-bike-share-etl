import pandas as pd
from io import StringIO
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ACCOUNT_URL = "https://hansontawiahstorage.blob.core.windows.net"
CONTAINER_NAME = "project-data"
INPUT_BLOB = "raw-data/202107-divvy-tripdata.csv"
OUTPUT_BLOB = "processed-data/divvy_trips_cleaned.csv"


# --------------------------------------------------
# CONNECT TO AZURE BLOB STORAGE
# --------------------------------------------------

credential = DefaultAzureCredential()

blob_service_client = BlobServiceClient(
    account_url=ACCOUNT_URL,
    credential=credential
)

print("Connected to Azure Blob Storage successfully.")


# --------------------------------------------------
# EXTRACT
# --------------------------------------------------

blob_client = blob_service_client.get_blob_client(
    container=CONTAINER_NAME,
    blob=INPUT_BLOB
)

downloaded_blob = blob_client.download_blob()
df = pd.read_csv(downloaded_blob)

original_rows = len(df)

print(f"Raw dataset loaded: {original_rows:,} rows")


# --------------------------------------------------
# TRANSFORM — DATA TYPES AND TRIP DURATION
# --------------------------------------------------

df["started_at"] = pd.to_datetime(df["started_at"])
df["ended_at"] = pd.to_datetime(df["ended_at"])

df["trip_duration_minutes"] = (
    df["ended_at"] - df["started_at"]
).dt.total_seconds() / 60


# --------------------------------------------------
# CLEAN — INVALID TRIP DURATIONS
# --------------------------------------------------

clean_df = df[
    (df["trip_duration_minutes"] > 0) &
    (df["trip_duration_minutes"] <= 1440)
].copy()

duration_removed = original_rows - len(clean_df)

print(f"Invalid-duration records removed: {duration_removed:,}")


# --------------------------------------------------
# CLEAN — INCOMPLETE END LOCATIONS
# --------------------------------------------------

missing_end_no_coords = clean_df[
    clean_df["end_station_name"].isnull() &
    ~clean_df[["end_lat", "end_lng"]].notnull().all(axis=1)
]

before_location_cleaning = len(clean_df)

clean_df = clean_df.drop(
    index=missing_end_no_coords.index
).copy()

location_removed = before_location_cleaning - len(clean_df)

print(f"Incomplete-location records removed: {location_removed:,}")


# --------------------------------------------------
# TRANSFORM — CREATE ANALYTICAL FEATURES
# --------------------------------------------------

clean_df["start_hour"] = clean_df["started_at"].dt.hour

clean_df["day_of_week"] = clean_df["started_at"].dt.day_name()

clean_df["day_type"] = clean_df["day_of_week"].apply(
    lambda day: "Weekend"
    if day in ["Saturday", "Sunday"]
    else "Weekday"
)


def classify_time_of_day(hour):
    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 21:
        return "Evening"
    else:
        return "Night"


clean_df["time_of_day"] = clean_df["start_hour"].apply(
    classify_time_of_day
)


# --------------------------------------------------
# DATA QUALITY SUMMARY
# --------------------------------------------------

print("\nDATA QUALITY SUMMARY")
print("--------------------")
print(f"Original rows: {original_rows:,}")
print(f"Final rows: {len(clean_df):,}")
print(f"Total rows removed: {original_rows - len(clean_df):,}")


# --------------------------------------------------
# ANALYTICS SUMMARY
# --------------------------------------------------

print("\nTRIPS BY RIDER TYPE")
print(clean_df["member_casual"].value_counts())

print("\nTRIPS BY DAY OF WEEK")
print(clean_df["day_of_week"].value_counts())

print("\nTRIPS BY TIME OF DAY")
print(clean_df["time_of_day"].value_counts())

print("\nAVERAGE TRIP DURATION BY RIDER TYPE")
print(
    clean_df.groupby("member_casual")[
        "trip_duration_minutes"
    ].mean().round(2)
)

print("\nTRIPS BY DAY AND RIDER TYPE")
print(
    clean_df.groupby(
        ["day_of_week", "member_casual"]
    ).size()
)


# --------------------------------------------------
# LOAD — UPLOAD PROCESSED DATA TO AZURE
# --------------------------------------------------

csv_buffer = StringIO()
clean_df.to_csv(csv_buffer, index=False)

output_blob_client = blob_service_client.get_blob_client(
    container=CONTAINER_NAME,
    blob=OUTPUT_BLOB
)

output_blob_client.upload_blob(
    csv_buffer.getvalue(),
    overwrite=True
)


# --------------------------------------------------
# PIPELINE COMPLETE
# --------------------------------------------------

print("\nETL PIPELINE COMPLETED SUCCESSFULLY")
print(f"Source: {INPUT_BLOB}")
print(f"Destination: {OUTPUT_BLOB}")
print(f"Rows loaded: {len(clean_df):,}")