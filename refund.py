import requests
import time
import json

# --- CONFIGURATION ---
# 1. Replace with your sk_live_xxx key for real money or sk_test_xxx for testing
SECRET_KEY = "sk_live_b49c66e2e43618e6166f455193856e1e2ab6d182" 
HEADERS = {
    "Authorization": f"Bearer {SECRET_KEY}",
    "Content-Type": "application/json"
}

# 2. BANK MAPPING DICTIONARY
# This converts common bank names into the 3-digit codes Paystack requires.
# You can add more banks to this list as needed.
BANK_MAP = {
    "access": "044",
    "gtb": "058",
    "gtbank": "058",
    "zenith": "057",
    "first bank": "011",
    "uba": "033",
    "kuda": "090267",
    "opay": "999992",
    "palmpay": "999991",
    "stanbic": "221",
    "fcmb": "214"
}

def run_refund_system(student_data):
    # This list will track everyone we SUCCESSFULLY sent a transfer command for
    program_records = []
    
    print(f"🚀 [LOG] {time.strftime('%H:%M:%S')} - Starting System for {len(student_data)} students.")

    for student in student_data:
        # Extract data from our input list
        provided_name = student['name']
        acc_num = student['account']
        raw_bank = student['bank_name'].lower().strip()
        
        # Look up the bank code. Defaults to "000" if the bank name isn't in our dictionary
        b_code = BANK_MAP.get(raw_bank, "000")
        
        # MATH: Refund is 2800. We take 100. Paystack needs the result in Kobo (Naira * 100).
        # Result: 2700 * 100 = 270,000 kobo
        payout_amount = (2800 - 100) * 100 

        # --- STEP 1: RESOLVE ACCOUNT (The Truth Filter) ---
        # This checks if the account number actually exists at that bank.
        verify_url = f"https://api.paystack.co/bank/resolve?account_number={acc_num}&bank_code={b_code}"
        
        try:
            v_req = requests.get(verify_url, headers=HEADERS)
            v_res = v_req.json()
            
            if v_res.get('status') is True:
                # The bank returns the official registered name
                bank_official_name = v_res['data']['account_name']
                print(f"✅ Verified: {bank_official_name} (Provided: {provided_name})")

                # --- STEP 2: CREATE TRANSFER RECIPIENT ---
                # Before sending money, Paystack needs to "save" this person as a recipient.
                recp_data = {
                    "type": "nuban",
                    "name": bank_official_name,
                    "account_number": acc_num,
                    "bank_code": b_code,
                    "currency": "NGN"
                }
                r_res = requests.post("https://api.paystack.co/transferrecipient", json=recp_data, headers=HEADERS).json()
                
                if r_res.get('status') is True:
                    recipient_code = r_res['data']['recipient_code']

                    # --- STEP 3: INITIATE THE ACTUAL TRANSFER ---
                    t_data = {
                        "source": "balance", 
                        "amount": payout_amount, 
                        "recipient": recipient_code, 
                        "reason": f"Refund for {provided_name}"
                    }
                    t_res = requests.post("https://api.paystack.co/transfer", json=t_data, headers=HEADERS).json()

                    if t_res.get('status') is True:
                        # Success! Record the account number so we can audit it later
                        program_records.append({"account": acc_num, "name": bank_official_name})
                        print(f"💰 Payout Triggered for {bank_official_name}")
                    else:
                        print(f"❌ Transfer Failed for {acc_num}: {t_res.get('message')}")
                else:
                    print(f"❌ Recipient Error for {acc_num}: {r_res.get('message')}")
            else:
                print(f"❌ Could not resolve {acc_num} at {raw_bank}. Check account info.")

        except Exception as e:
            print(f"⚠️ Critical System Error on {acc_num}: {e}")
        
        # Brief pause to avoid hitting API rate limits
        time.sleep(1)

    # --- STEP 4: AUDIT & RECONCILIATION ---
    # We compare our "Program Records" against Paystack's "Actual Logs" to calculate accuracy.
    print("\n" + "="*40)
    print("📊 GENERATING FINAL AUDIT REPORT")
    print("="*40)
    
    # Wait 5 seconds for Paystack's servers to fully process the transactions
    time.sleep(5) 
    
    log_res = requests.get("https://api.paystack.co/transfer", headers=HEADERS).json()
    
    # Extract list of accounts that actually appear in Paystack's successful/pending logs
    actual_logs = log_res.get('data', [])
    paystack_confirmed = [
        item['recipient']['details']['account_number'] 
        for item in actual_logs if item['status'] in ['success', 'pending', 'processing']
    ]
    
    # Compare intended list vs actual log list
    intended_accs = [r['account'] for r in program_records]
    matches = set(intended_accs) & set(paystack_confirmed)
    mismatches = set(intended_accs) - set(paystack_confirmed)
    
    # Calculate accuracy percentage
    total_input = len(student_data)
    accuracy = (len(matches) / total_input) * 100 if total_input > 0 else 0

    # Save details to a file for the HOC
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "accuracy": f"{accuracy}%",
        "paid_count": len(matches),
        "failed_matches": list(mismatches),
        "verified_names": program_records
    }
    
    with open("refund_audit_report.json", "w") as f:
        json.dump(report, f, indent=4)

    print(f"Final System Accuracy: {accuracy}% 🎯")
    print(f"Matched Transfers: {len(matches)}")
    print(f"Unmatched/Missed: {len(mismatches)}")
    print("Full report saved to 'refund_audit_report.json'")

# --- INPUT DATA ---
# Replace this with the real list from the HOC.
# IMPORTANT: 'bank_name' must match a key in the BANK_MAP dictionary above.
students_to_refund = [
    {"name": "Adebayo Victor", "account": "8136390030", "bank_name": "palmpay"},
    {"name": "Adebayo Victor", "account": "8136390030", "bank_name": "Opay"}
]

if __name__ == "__main__":
    run_refund_system(students_to_refund)