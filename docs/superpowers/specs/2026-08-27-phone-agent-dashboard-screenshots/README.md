# Owner dashboard — every screen, both sizes

These are photographs of the phone agent's owner dashboard, taken in a real
Chrome against a real running instance of the product.

**Everything on these screens is fiction.** No customer, no call and no phone
number here is real. They come from `tests/e2e/run_dashboard_fixture.py`, which
starts the product against a throwaway settings file and a throwaway database:

* two invented businesses, **Acme Plumbing** and **Riverside Dental**;
* callers with `+1555…` numbers, which are the range reserved for drama;
* call ids that all begin `CAtest…`;
* a model whose label says "test only", which is why the orange safety banner
  is on the Overview — that banner is a real feature, not a mock-up;
* a message alert that really failed to send to `push.acme.invalid`, a domain
  that does not exist, which is why "Mark as seen" is on screen;
* calls spread across the last seven days, each with a length — invented
  dates and invented lengths, written by the fixture's own `backdate()` so
  that the seven-day chart has seven days in it and the call log shows
  lengths a person would recognise. The store stamps its own clock, so
  without this every call would sit at the same minute, `0:00` long.

`calls-pagination-desktop` is the one picture with more in it than the fixture
seeds: 55 extra "Name not given / hung up / 1:35" rows were added to the
throwaway database by hand to make a second page exist, and deleted again
afterwards. They are invented like everything else.

Nothing in these pictures was read from the live line, and nothing in the
fixture is written anywhere near it.

## Sizes

| suffix | viewport | what it stands for |
| --- | --- | --- |
| `-desktop` | 1440 × 900 | a laptop, the side rail visible |
| `-mobile` | 390 × 844 | a phone, the rail replaced by a bottom tab bar |

The desktop pictures are the whole page, scrolled out into one image. The phone
ones are one screenful, because the tab bar is fixed to the bottom of the
window: in a stitched full-page image it lands in the middle of the picture,
which is a lie about where it actually sits.

## The screens

| file | what it shows |
| --- | --- |
| `sign-in-…` | the access-code page |
| `sign-in-error-…` | a wrong code, refused in place |
| `sign-in-lockout-…` | too many wrong codes: the form closes for a minute |
| `overview-…` | line status, the safety banner, today, the latest messages |
| `calls-…` | the call log with its filters and the show-test switch |
| `calls-pagination-desktop` | the same list with 63 calls in it, paged fifty at a time |
| `call-detail-…` | one call: the conversation, the message, how it went |
| `messages-…` | the inbox and its new / in progress / done tabs |
| `settings-…` | how the line answers, one section at a time |
| `settings-error-…` | a refused save, with the typing still on screen |
| `hours-…` | opening hours and what happens out of hours |
| `numbers-…` | which business each phone number answers for |
| `notifications-…` | where messages are sent, and the send-test result |
| `brain-…` | the model that answers every call (whole-line sign-in only) |
| `brain-confirm-…` | the confirm step before the model changes |
| `activity-…` | everything that has changed on the line |
| `activity-scoped-…` | the same screen for an owner of ONE business — the other business's changes are not there |
| `business-delete-…` | removing a business, and the refusal when the name is mistyped |

## Taking them again

```
# terminal 1 — it prints the pid to stop it with
cd <worktree>
PYTHONPATH=<worktree>:<worktree>/src \
  python tests/e2e/run_dashboard_fixture.py /tmp/dash-work 8931

# terminal 2 — the checks a machine can do on its own
python tests/e2e/phone_dashboard_checks.py http://127.0.0.1:8931
```

Then drive a browser at `http://127.0.0.1:8931/` and sign in with `line-code`
(the whole line) or `acme-code` (Acme Plumbing only).
