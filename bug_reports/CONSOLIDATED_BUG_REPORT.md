# Bug Report — Pretty Good AI Voice Agent

Calls analyzed: 12
Calls surfacing at least one issue: 6

---

## CA523e79f697090c6250dd82d3db84e17c.txt — Straightforward medication refill

BUG: The agent failed to verify the patient's identity using alternative methods when the date of birth was not provided.
SEVERITY: Medium
TIMESTAMP: [00:33]
DETAILS: The patient offered to verify their identity using alternative information such as medication details or pharmacy information. The agent should have attempted to verify the patient's identity using these alternative methods instead of immediately transferring the call. This could lead to unnecessary call transfers and patient frustration.

BUG: The agent prematurely ended the call without ensuring the patient was connected to the patient support team.
SEVERITY: High
TIMESTAMP: [01:10]
DETAILS: The agent stated it would transfer the patient to the patient support team but instead ended the call. This could result in the patient not receiving the necessary assistance for their medication refill request, potentially impacting their health if the medication is not refilled in a timely manner. The agent should have ensured the transfer was successful before ending the call.

---

## CA67420a89d53adfb44e364d13f1293d5f.txt — Insurance and copay question

BUG: The agent provided an incorrect phone number for insurance verification.  
SEVERITY: High  
TIMESTAMP: [00:52]  
DETAILS: The agent gave a phone number "1-234-RECOVERY-WAY" which is not a valid phone number format. This could lead to patient confusion and inability to verify insurance information. The agent should have provided a correct and valid phone number for the front desk or the billing department for insurance verification.

BUG: The agent failed to properly transfer the call to the patient support team.  
SEVERITY: Medium  
TIMESTAMP: [01:14]  
DETAILS: The agent attempted to transfer the call to the patient support team but instead connected the caller to a test line that did not provide the needed information and ended the call. This left the patient without the necessary information and without a clear path to obtain it. The agent should have ensured a successful transfer to the correct department or provided an alternative solution.

BUG: The agent did not confirm whether the office accepts Anthem BlueCross BlueShield PPO.  
SEVERITY: Medium  
TIMESTAMP: [01:29]  
DETAILS: The patient repeatedly asked if the office accepts Anthem BlueCross BlueShield PPO, but the agent did not provide a direct answer or confirm acceptance. Instead, the agent redirected the patient to a website without addressing the specific insurance query. The agent should have either confirmed the acceptance of the insurance or directed the patient to the appropriate department for verification.

---

## CA9dcc430f662cde3f64947f11d60f86bb.txt — Rescheduling an existing appointment

BUG: The agent failed to connect the patient to the patient support team and instead ended the call.  
SEVERITY: High  
TIMESTAMP: [01:25]  
DETAILS: The agent stated it would transfer the patient to the patient support team but instead connected the call to a test line and then ended the call. This is a critical failure as it leaves the patient without a resolution to their request to reschedule an appointment. The agent should have successfully transferred the call to a live representative or provided clear instructions on what the patient should do next.

---

## CAa6bda09b70678bca4cb03fe69195de48.txt — Canceling an appointment (agent may push back)

BUG: The agent failed to confirm the cancellation request verbally and instead attempted to transfer the call to a non-functional test line.
SEVERITY: High
TIMESTAMP: [01:17]
DETAILS: The agent did not confirm the cancellation request as instructed and instead transferred the caller to a test line, which is not a valid action for handling a cancellation request. This could lead to the appointment not being canceled, causing inconvenience to the patient and potential scheduling conflicts for the clinic. The agent should have confirmed the cancellation verbally and assured the patient that the request was documented for follow-up by the clinic support team.

---

## CAe1e21351229304b22daea0cc4dbc43eb.txt — EDGE CASE: caller interrupts mid-sentence (barge-in)

BUG: The agent failed to acknowledge the patient's request to reschedule for next week and instead offered to connect to the patient support team without addressing the specific request.
SEVERITY: Medium
TIMESTAMP: [02:01]
DETAILS: The patient interrupted the agent to request a rescheduling for next week. The agent should have acknowledged this request and either proceeded to reschedule the appointment or confirmed the details before connecting to the patient support team. Instead, the agent ignored the specific request and continued with a generic offer to connect to support, which could lead to patient frustration and inefficiency.

BUG: The agent abruptly ended the call without ensuring the patient's request was addressed or confirming the transfer to the patient support team.
SEVERITY: High
TIMESTAMP: [02:30]
DETAILS: The agent stated "That's for you now" and then ended the call with "Goodbye," without confirming that the patient was successfully connected to the support team or that their request was being handled. This could leave the patient without the assistance they needed and reflects poor call handling, as a competent receptionist would ensure the patient's needs were met before ending the call.

---

## CAf2e26c1733c2512f46e0e791d9057765.txt — EDGE CASE: two separate requests in one call

BUG: The agent failed to retain context and did not handle the second request for an inhaler refill after the initial appointment rescheduling request.
SEVERITY: Medium
TIMESTAMP: [00:34]
DETAILS: The patient requested both an appointment rescheduling and an inhaler refill. The agent did not address the refill request after failing to reschedule the appointment due to lack of patient identification. A competent receptionist would have acknowledged both requests and attempted to address them sequentially or informed the patient of the next steps for both issues.

BUG: The agent did not attempt to verify the patient's identity using existing records or alternative methods after the patient could not provide their full name and date of birth.
SEVERITY: High
TIMESTAMP: [00:52]
DETAILS: The patient suggested using existing records to verify their identity, but the agent did not attempt this or offer any alternative verification methods. This is critical as it prevents the agent from assisting with the patient's requests, which could lead to missed appointments or medication refills, impacting patient care.

BUG: The agent did not confirm the patient's contact information before ending the call.
SEVERITY: Medium
TIMESTAMP: [01:19]
DETAILS: The patient requested follow-up using the phone number on the screen, but the agent did not confirm or repeat the number back to ensure accuracy. This could lead to communication issues if the contact information is incorrect or not properly recorded. A competent receptionist would confirm the contact details before concluding the call.