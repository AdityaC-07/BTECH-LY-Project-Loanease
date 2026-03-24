# Chatbot Integration Flow (No Frontend Code Changes Made)

Use this service after the Underwriting Agent returns approval.

Optional shortcut:

- Use `POST /negotiate/start-from-underwriting` if you prefer one call from chat that triggers underwriting + negotiation start.

## 1) Start Offer Card

Call `POST /negotiate/start` using `risk_score` and `risk_tier` from `/assess`.
Render opening offer card with:

- `opening_offer.rate`
- `opening_offer.emi_formatted`
- `opening_offer.tenure_months`
- `opening_offer.total_payable_formatted`
- `reasoning`
- `rounds_remaining`

Suggested buttons:

- `Accept` -> `POST /negotiate/accept`
- `Negotiate` -> `POST /negotiate/counter`

## 2) Counter Loop

On free-text message or Negotiate click:

- Send `applicant_message` to `POST /negotiate/counter`.
- Read `detected_intent` and render chatbot response accordingly.
- Update offer card using `counter_offer` payload.
- Show savings badge from `counter_offer.savings_vs_opening_formatted`.
- Show `rounds_remaining` and disable negotiate button when `can_negotiate_further=false`.

## 3) Accept Offer

On accept intent/button:

- Call `POST /negotiate/accept`.
- Show success message and `sanction_reference`.
- Redirect to dashboard or next sanction workflow.

## 4) Escalation

When intent is `ESCALATION_REQUEST` or user asks for human:

- Call `POST /negotiate/escalate`.
- Display escalation ticket and lock further automated negotiation actions.

## Intent Mapping Returned by API

- `COUNTER_REQUEST`
- `TENURE_QUERY`
- `ACCEPTANCE`
- `ESCALATION_REQUEST`
- `FINAL_OFFER_REQUEST`
- `HESITATION`
- `UNKNOWN`
