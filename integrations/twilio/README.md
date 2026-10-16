# Twilio / Vapi boundary for OrderNexa

OrderNexa does **not** require Twilio credentials in the FastAPI backend for the current voice design. Twilio terminates telephony and Vapi owns the conversational session. Vapi calls the two guarded OrderNexa HTTP contracts documented in `../vapi/OrderNexa_Vapi_Tool_Contracts.json`.

Production rule: keep `VOICE_SERVER_SECRET` only in OrderNexa `.env` and the Vapi secret/header configuration. Do not put it in prompts, source control, workflow JSON, screenshots, or Twilio Studio text.

The supported voice path is deliberately review-only:

`Twilio phone number -> Vapi assistant -> OrderNexa safe status lookup / change-request endpoint -> Voice Review -> human/policy workflow`

A customer request such as “change quantity to 55” must create a review request. It must never update the Odoo order directly.
