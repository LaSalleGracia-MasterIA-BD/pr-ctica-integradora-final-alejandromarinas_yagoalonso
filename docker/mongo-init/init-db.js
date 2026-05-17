// Initialize hospital database, collections, and indexes.
//
// Pipeline runs and data quality summary live in SQLite (see ADR-004:
// polyglot persistence). MongoDB owns patients/admissions/radiographies
// and the rejected_records collection (with raw_data heterogeneous JSON).

db = db.getSiblingDB('hospital');

// Collections owned by MongoDB
db.createCollection('patients');
db.createCollection('rejected_records');

// Unique index on external_id for patients (idempotent upserts)
db.patients.createIndex({ external_id: 1 }, { unique: true });

// Soft cross-DB reference to SQLite pipeline_runs.id (a UUID string).
// No FK enforcement; the index keeps "find rejects for this run" fast.
db.rejected_records.createIndex({ pipeline_run_id: 1 });

// Index on the radiography object_key inside the embedded array. Used by
// the classify endpoint (POST /radiographies/classify) to locate the
// right subdocument via arrayFilters, and by the reader to get the
// persisted classification for a given key.
db.patients.createIndex({ 'radiographies.minio_object_key': 1 });

print('Hospital database initialized: collections and indexes created.');
