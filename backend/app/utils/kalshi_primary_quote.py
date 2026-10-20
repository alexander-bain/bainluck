"""#10090: custody of a normal-policy Kalshi quote observation, never an estimator.

A book callback may select a cached original trade under the ordinary price
policy (`_kalshi_yes_probability`). That accepted selection carries an identity
from the socket; the consumer records it here as received, then as landed (the
exact committed observation) or held (the actually applied overlay bound). The
blend refresher may let the bundled Challenger primary row speak at that price
only after that observation has itself landed or passed held admission; a
stored price that merely equals it proves nothing. No clock is inferred.
"""


class PrimaryQuoteCustody:
    def __init__(self):
        self.received = {}
        self.landed = {}
        self.held = {}

    def retain(self, outcome_ids):
        allowed = set(outcome_ids)
        for table in (self.received, self.landed, self.held):
            for oid in set(table) - allowed:
                del table[oid]

    def receive(self, oid, quote):
        identity = quote.get('_primary_quote_identity')
        if identity is None:
            self.received.pop(oid, None)
        else:
            self.received[oid] = (identity, quote['_primary_quote_probability'])

    def snapshot(self, ids):
        return {oid: self.received.get(oid) for oid in ids}

    def pending(self, snapshot):
        return {oid for oid, entry in snapshot.items()
                if entry is not None and self.landed.get(oid, (None, None))[0] != entry}

    def committed(self, snapshot, observations):
        for oid, observed_at in observations.items():
            entry = snapshot.get(oid)
            if entry is not None:
                self.landed[oid] = (entry, observed_at)
            else:
                self.landed.pop(oid, None)
            self.held.pop(oid, None)

    def admitted(self, snapshot, quotes):
        for oid, (price, bound) in quotes.items():
            entry = snapshot.get(oid)
            if entry is not None and entry[1] == price:
                self.held[oid] = (entry, bound)

    def eligible(self, row, entry, held_quotes=None, *, overlaid=False):
        if entry is None or getattr(row, 'current_probability', None) is None:
            return False
        if float(row.current_probability) != entry[1]:
            return False
        if getattr(row, 'resolution_source', None) is not None or getattr(row, 'is_winner', None) is not None:
            return False
        observed = getattr(row, 'last_updated', None)
        if not overlaid and self.landed.get(row.id) == (entry, observed):
            return True
        admitted = self.held.get(row.id)
        if not overlaid or admitted is None or admitted[0] != entry or held_quotes is None:
            return False
        bound = admitted[1]
        return (held_quotes._quotes.get(row.id) == (round(float(entry[1]), 6), bound)
                and hasattr(observed, 'timestamp') and observed.timestamp() == bound)
