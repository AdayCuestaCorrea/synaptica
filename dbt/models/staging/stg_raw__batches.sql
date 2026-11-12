-- Daily batch files present in the raw store, per source/kind and date.
select * from {{ read_batch_files() }}
