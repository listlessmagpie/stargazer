# Family 3: connected charts

Registered 2026-10-12, before the event ledger holds any acts.

**Question.** When a person or body in the library acts (decides, speaks, trades, lists,
buys), what is the sky doing to their chart, to the chart of the thing acted on, and to the
charts of what they hold, and does the market move more after acts made under some contacts
than others?

**Acts, first set.** FOMC decisions (dated from the Fed's own calendars, library/events_fomc.jsonl).
Then, as the ledger grows: Bitcoin halvings, listings, ETF approvals, disclosed trades of the
most active members of Congress, Form 4 insider trades of library people, Strategy's Bitcoin
purchases, policy posts and coin posts of library people with a timestamp.

**Measure.** For each act: the absolute market move over 1 and 5 trading days after it, for
the instruments connected to the actor by an edge in the library. For each contact (transiting
body, natal point, aspect) active on the act's day on the actor's chart: the mean absolute move
after acts with that contact minus acts without it.

**Luck rule.** Shuffle the act dates against the actor's transit series 100 times (keeping the
number and spacing of acts). A contact counts only if the real difference exceeds the 95th
percentile of the shuffled differences, and the family as a whole counts only if the number of
passing contacts exceeds the shuffled 95th percentile.

**Minimums.** At least 20 acts per actor before any contact is read. FOMC has about 170 since
2005 and is the first actor that qualifies.

**What it earns.** A contact that passes earns a forward log line: before each upcoming act
(FOMC dates are published ahead), the log states which contacts will be active and what size
of move the record expects. Scored after. It reaches the paper book only through family 2's
occasion rule applied to the act plus contact pairing.

**Expected result, stated now.** Unknown. This is the question nobody has run with a luck test.
