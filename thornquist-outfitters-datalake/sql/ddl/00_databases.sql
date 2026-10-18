-- Run once per Learner Lab session (Athena workgroup: thornquist-wg).
-- ${BUCKET} is replaced by deploy/deploy.sh; replace by hand if running in the console.
-- If Aish's setup already created these databases, these statements are no-ops.
CREATE DATABASE IF NOT EXISTS thornquist_trusted    LOCATION 's3://${BUCKET}/trusted/';
CREATE DATABASE IF NOT EXISTS thornquist_quarantine LOCATION 's3://${BUCKET}/quarantine/';
CREATE DATABASE IF NOT EXISTS thornquist_curated    LOCATION 's3://${BUCKET}/curated/';
