
import boto3
import urllib.parse

s3 = boto3.client("s3")

BUCKET_NAME = "thornquist-outfitters-datalake-672869298071"
SOURCE_PREFIX = "landing/"
DESTINATION_PREFIX = "raw/"


def lambda_handler(event, context):
    copied_files = []

    for record in event.get("Records", []):
        source_bucket = record["s3"]["bucket"]["name"]
        source_key = urllib.parse.unquote_plus(
            record["s3"]["object"]["key"]
        )

        if source_bucket != BUCKET_NAME:
            continue

        if not source_key.startswith(SOURCE_PREFIX):
            continue

        if not source_key.lower().endswith(".json"):
            continue

        destination_key = (
            DESTINATION_PREFIX
            + source_key[len(SOURCE_PREFIX):]
        )

        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={
                "Bucket": source_bucket,
                "Key": source_key
            },
            Key=destination_key
        )

        copied_files.append(destination_key)

    return {
        "statusCode": 200,
        "copied_files": copied_files
    }
