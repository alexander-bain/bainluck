# In-memory protocol fixture only

`authority_model.py` is the process-local snapshot/retention fixture from the monotonic GET contract experiment. It supplies fresh remaining-budget and invalidation cases to test_server_remaining.py. It is not a real Redis adapter, SQL transaction, current route implementation, or a replacement for the separately proposed atomic store. Do not wire it into production routes.
