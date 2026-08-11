| # | Method | Endpoint | Path | Tags | Summary | Response Model |
|---|---|---|---|---|---|---|---|
| 1 | GET | N/A | /api/v1/admin/audit-logs | admin-audit | List Audit Logs |  |
| 2 | POST | N/A | /api/v1/admin/audit-logs/export | admin-audit | Export Audit Logs |  |
| 3 | GET | N/A | /api/v1/admin/audit-logs/export | admin-audit | Export Audit Logs |  |
| 4 | GET | N/A | /api/v1/admin/audit-logs/{entry_id} | admin-audit | Get Audit Log |  |
| 5 | GET | N/A | /api/v1/admin/dashboard/adoption-stats | admin-dashboard | Get Adoption Stats |  |
| 6 | GET | N/A | /api/v1/admin/dashboard/charts | admin-dashboard | Get Charts |  |
| 7 | GET | N/A | /api/v1/admin/dashboard/donation-summary | admin-dashboard | Get Donation Summary |  |
| 8 | GET | N/A | /api/v1/admin/dashboard/foster-stats | admin-dashboard | Get Foster Stats |  |
| 9 | GET | N/A | /api/v1/admin/dashboard/grievance-stats | admin-dashboard | Get Grievance Stats |  |
| 10 | GET | N/A | /api/v1/admin/dashboard/inventory-alerts | admin-dashboard | Get Inventory Alerts |  |
| 11 | GET | N/A | /api/v1/admin/dashboard/kpis | admin-dashboard | Get Kpis |  |
| 12 | GET | N/A | /api/v1/admin/dashboard/lost-found-stats | admin-dashboard | Get Lost Found Stats |  |
| 13 | GET | N/A | /api/v1/admin/dashboard/medical-stats | admin-dashboard | Get Medical Stats |  |
| 14 | GET | N/A | /api/v1/admin/dashboard/metrics | admin-dashboard | Get System Metrics |  |
| 15 | GET | N/A | /api/v1/admin/dashboard/notification-summary | admin-dashboard | Get Notification Summary |  |
| 16 | GET | N/A | /api/v1/admin/dashboard/recent-activity | admin-dashboard | Get Recent Activity |  |
| 17 | GET | N/A | /api/v1/admin/dashboard/rescue-stats | admin-dashboard | Get Rescue Stats |  |
| 18 | GET | N/A | /api/v1/admin/dashboard/shelter-stats | admin-dashboard | Get Shelter Stats |  |
| 19 | GET | N/A | /api/v1/admin/dashboard/summary | admin-dashboard | Get Summary |  |
| 20 | GET | N/A | /api/v1/admin/dashboard/volunteer-stats | admin-dashboard | Get Volunteer Stats |  |
| 21 | GET | N/A | /api/v1/admin/permissions | admin | List Permissions |  |
| 22 | GET | N/A | /api/v1/admin/roles | admin | List Roles |  |
| 23 | POST | N/A | /api/v1/admin/roles | admin | Create Role |  |
| 24 | GET | N/A | /api/v1/admin/roles/{role_id} | admin | Get Role |  |
| 25 | PUT | N/A | /api/v1/admin/roles/{role_id} | admin | Update Role |  |
| 26 | DELETE | N/A | /api/v1/admin/roles/{role_id} | admin | Delete Role |  |
| 27 | GET | N/A | /api/v1/admin/users | admin | List Users |  |
| 28 | POST | N/A | /api/v1/admin/users | admin | Create User |  |
| 29 | GET | N/A | /api/v1/admin/users/{user_id} | admin | Get User |  |
| 30 | PUT | N/A | /api/v1/admin/users/{user_id} | admin | Update User |  |
| 31 | DELETE | N/A | /api/v1/admin/users/{user_id} | admin | Delete User |  |
| 32 | POST | N/A | /api/v1/adoptions | adoptions | Apply For Adoption |  |
| 33 | GET | N/A | /api/v1/adoptions | adoptions | List Applications |  |
| 34 | DELETE | N/A | /api/v1/adoptions/admin/adoptions/{app_id} | adoptions | Soft Delete Application |  |
| 35 | POST | N/A | /api/v1/adoptions/bulk/delete | adoptions | Bulk Delete Applications |  |
| 36 | POST | N/A | /api/v1/adoptions/bulk/status-update | adoptions | Bulk Update Application Status |  |
| 37 | GET | N/A | /api/v1/adoptions/my | adoptions | List My Applications |  |
| 38 | GET | N/A | /api/v1/adoptions/nearby-shelters | adoptions | Find Nearby Shelters |  |
| 39 | GET | N/A | /api/v1/adoptions/{app_id} | adoptions | Get Application |  |
| 40 | PUT | N/A | /api/v1/adoptions/{app_id} | adoptions | Update Application |  |
| 41 | DELETE | N/A | /api/v1/adoptions/{app_id} | adoptions | Soft Delete Application |  |
| 42 | GET | N/A | /api/v1/adoptions/{app_id}/agreement | adoptions | Get Adoption Agreement |  |
| 43 | PUT | N/A | /api/v1/adoptions/{app_id}/fee | adoptions | Update Adoption Fee |  |
| 44 | POST | N/A | /api/v1/adoptions/{app_id}/follow-ups | adoptions | Create Follow Up |  |
| 45 | GET | N/A | /api/v1/adoptions/{app_id}/follow-ups | adoptions | Get Follow Ups |  |
| 46 | POST | N/A | /api/v1/adoptions/{app_id}/follow-ups/{follow_up_id}/proof | adoptions | Submit Follow Up Proof |  |
| 47 | POST | N/A | /api/v1/adoptions/{app_id}/scores | adoptions | Add Score |  |
| 48 | GET | N/A | /api/v1/adoptions/{app_id}/scores | adoptions | Get Scores |  |
| 49 | PATCH | N/A | /api/v1/adoptions/{app_id}/status | adoptions | Update Application Status |  |
| 50 | POST | N/A | /api/v1/auth/email/verify/confirm | auth | Confirm Email Verification |  |
| 51 | POST | N/A | /api/v1/auth/email/verify/request | auth | Request Email Verification |  |
| 52 | POST | N/A | /api/v1/auth/login | auth | Login |  |
| 53 | POST | N/A | /api/v1/auth/logout | auth | Logout |  |
| 54 | POST | N/A | /api/v1/auth/logout-all | auth | Logout All |  |
| 55 | GET | N/A | /api/v1/auth/me | auth | Get Me |  |
| 56 | PUT | N/A | /api/v1/auth/me | auth | Update Profile |  |
| 57 | POST | N/A | /api/v1/auth/mfa/disable | auth | Disable Mfa |  |
| 58 | POST | N/A | /api/v1/auth/mfa/enroll | auth | Enroll Mfa |  |
| 59 | POST | N/A | /api/v1/auth/mfa/enroll/confirm | auth | Confirm Mfa Enrollment |  |
| 60 | POST | N/A | /api/v1/auth/mfa/verify | auth | Verify Mfa Login |  |
| 61 | GET | N/A | /api/v1/auth/oauth/accounts | auth | List Oauth Accounts |  |
| 62 | DELETE | N/A | /api/v1/auth/oauth/accounts/{account_id} | auth | Unlink Oauth Account |  |
| 63 | POST | N/A | /api/v1/auth/oauth/link | auth | Link Oauth Account |  |
| 64 | POST | N/A | /api/v1/auth/oauth/login | auth | Oauth Login |  |
| 65 | POST | N/A | /api/v1/auth/password/change | auth | Change Password |  |
| 66 | POST | N/A | /api/v1/auth/password/reset/confirm | auth | Confirm Password Reset |  |
| 67 | POST | N/A | /api/v1/auth/password/reset/request | auth | Request Password Reset |  |
| 68 | POST | N/A | /api/v1/auth/refresh | auth | Refresh |  |
| 69 | POST | N/A | /api/v1/auth/register | auth | Register |  |
| 70 | GET | N/A | /api/v1/auth/sessions | auth | List Sessions |  |
| 71 | DELETE | N/A | /api/v1/auth/sessions/{session_id} | auth | Revoke Session |  |
| 72 | POST | N/A | /api/v1/companion-pets | companion-pets | Create an owner companion pet |  |
| 73 | GET | N/A | /api/v1/companion-pets | companion-pets | List companion pets visible to the caller |  |
| 74 | GET | N/A | /api/v1/companion-pets/appointments | companion-pets | List authorized veterinary appointments |  |
| 75 | POST | N/A | /api/v1/companion-pets/appointments | companion-pets | Book a veterinary appointment |  |
| 76 | GET | N/A | /api/v1/companion-pets/appointments/{appointment_id} | companion-pets | Get an authorized appointment |  |
| 77 | POST | N/A | /api/v1/companion-pets/appointments/{appointment_id}/cancel | companion-pets | Cancel an appointment |  |
| 78 | POST | N/A | /api/v1/companion-pets/appointments/{appointment_id}/confirm | companion-pets | Confirm an appointment as clinic staff |  |
| 79 | GET | N/A | /api/v1/companion-pets/clinics | companion-pets | List active veterinary clinics |  |
| 80 | POST | N/A | /api/v1/companion-pets/clinics | companion-pets | Create a veterinary clinic directory entry |  |
| 81 | PATCH | N/A | /api/v1/companion-pets/clinics/{clinic_id} | companion-pets | Update a veterinary clinic directory entry |  |
| 82 | DELETE | N/A | /api/v1/companion-pets/clinics/{clinic_id} | companion-pets | Soft-delete a veterinary clinic directory entry |  |
| 83 | POST | N/A | /api/v1/companion-pets/clinics/{clinic_id}/memberships | companion-pets | Authorize a user for a veterinary clinic |  |
| 84 | DELETE | N/A | /api/v1/companion-pets/medical-records/{record_id} | companion-pets | Soft-delete an authorized medical-history record |  |
| 85 | POST | N/A | /api/v1/companion-pets/safety-tag/scan | companion-pets | Privacy-safe public QR safety-tag scan |  |
| 86 | GET | N/A | /api/v1/companion-pets/{pet_id} | companion-pets | Get an authorized companion pet profile |  |
| 87 | PATCH | N/A | /api/v1/companion-pets/{pet_id} | companion-pets | Update an authorized companion pet profile |  |
| 88 | DELETE | N/A | /api/v1/companion-pets/{pet_id} | companion-pets | Soft-delete an owned companion pet |  |
| 89 | GET | N/A | /api/v1/companion-pets/{pet_id}/medical-files | companion-pets | List authorized medical-history files |  |
| 90 | POST | N/A | /api/v1/companion-pets/{pet_id}/medical-files/upload-url | companion-pets | Request a presigned medical-history upload |  |
| 91 | PUT | N/A | /api/v1/companion-pets/{pet_id}/medical-files/{file_id}/confirm | companion-pets | Confirm a medical-history upload |  |
| 92 | POST | N/A | /api/v1/companion-pets/{pet_id}/medical-records | companion-pets | Create a medical-history record |  |
| 93 | GET | N/A | /api/v1/companion-pets/{pet_id}/medical-records | companion-pets | List a pet's authorized medical history |  |
| 94 | POST | N/A | /api/v1/companion-pets/{pet_id}/reminders | companion-pets | Create a vaccination or medication reminder |  |
| 95 | GET | N/A | /api/v1/companion-pets/{pet_id}/reminders | companion-pets | List vaccination and medication reminders |  |
| 96 | DELETE | N/A | /api/v1/companion-pets/{pet_id}/reminders/{reminder_id} | companion-pets | Soft-delete a vaccination or medication reminder |  |
| 97 | POST | N/A | /api/v1/companion-pets/{pet_id}/safety-tag | companion-pets | Provision or rotate a QR safety tag |  |
| 98 | GET | N/A | /api/v1/companion-pets/{pet_id}/safety-tag | companion-pets | Read safety-tag metadata without revealing its token |  |
| 99 | GET | N/A | /api/v1/dashboards/adoption | dashboards | Get Adoption Dashboard |  |
| 100 | GET | N/A | /api/v1/dashboards/donor | dashboards | Get Donor Dashboard |  |
| 101 | GET | N/A | /api/v1/dashboards/executive | dashboards | Get Executive Dashboard |  |
| 102 | GET | N/A | /api/v1/dashboards/finance | dashboards | Get Finance Dashboard |  |
| 103 | GET | N/A | /api/v1/dashboards/foster | dashboards | Get Foster Dashboard |  |
| 104 | GET | N/A | /api/v1/dashboards/inventory | dashboards | Get Inventory Dashboard |  |
| 105 | GET | N/A | /api/v1/dashboards/medical | dashboards | Get Medical Dashboard |  |
| 106 | GET | N/A | /api/v1/dashboards/operations | dashboards | Get Operations Dashboard |  |
| 107 | GET | N/A | /api/v1/dashboards/public | dashboards | Get Public Dashboard |  |
| 108 | GET | N/A | /api/v1/dashboards/rescue | dashboards | Get Rescue Dashboard |  |
| 109 | GET | N/A | /api/v1/dashboards/rescue/stream | dashboards | Stream Rescue Dashboard |  |
| 110 | GET | N/A | /api/v1/dashboards/shelter | dashboards | Get Shelter Dashboard |  |
| 111 | GET | N/A | /api/v1/dashboards/staff | dashboards | Get Staff Dashboard |  |
| 112 | GET | N/A | /api/v1/dashboards/volunteer | dashboards | Get Volunteer Dashboard |  |
| 113 | POST | N/A | /api/v1/dogs | dogs | Register Dog |  |
| 114 | GET | N/A | /api/v1/dogs | dogs | List Dogs |  |
| 115 | GET | N/A | /api/v1/dogs/admin/dogs/{dog_id} | dogs | Get Dog |  |
| 116 | PATCH | N/A | /api/v1/dogs/admin/dogs/{dog_id}/status | dogs | Update Dog Status |  |
| 117 | POST | N/A | /api/v1/dogs/bulk/delete | dogs | Bulk Delete Dogs |  |
| 118 | POST | N/A | /api/v1/dogs/bulk/status-update | dogs | Bulk Update Dog Status |  |
| 119 | GET | N/A | /api/v1/dogs/{dog_id} | dogs | Get Dog |  |
| 120 | PUT | N/A | /api/v1/dogs/{dog_id} | dogs | Update Dog |  |
| 121 | DELETE | N/A | /api/v1/dogs/{dog_id} | dogs | Soft Delete Dog |  |
| 122 | GET | N/A | /api/v1/dogs/{dog_id}/public-scan | dogs | Privacy-safe public dog QR scan |  |
| 123 | GET | N/A | /api/v1/dogs/{dog_id}/qr-image | dogs | Generate a staff-only dog profile QR image |  |
| 124 | PATCH | N/A | /api/v1/dogs/{dog_id}/status | dogs | Update Dog Status |  |
| 125 | GET | N/A | /api/v1/dogs/{dog_id}/timeline | dogs | Get Dog Timeline |  |
| 126 | POST | N/A | /api/v1/dogs/{dog_id}/weight | dogs | Record Dog Weight |  |
| 127 | GET | N/A | /api/v1/dogs/{dog_id}/weights | dogs | Get Dog Weight History |  |
| 128 | POST | N/A | /api/v1/donations | donations | Record Manual Donation |  |
| 129 | GET | N/A | /api/v1/donations | donations | List All Donations |  |
| 130 | POST | N/A | /api/v1/donations/bulk/status-update | donations | Bulk Update Donation Status |  |
| 131 | GET | N/A | /api/v1/donations/campaigns | donations | List Public Campaigns |  |
| 132 | POST | N/A | /api/v1/donations/campaigns | donations | Create Campaign |  |
| 133 | GET | N/A | /api/v1/donations/campaigns/manage | donations | List All Campaigns |  |
| 134 | GET | N/A | /api/v1/donations/campaigns/{campaign_id} | donations | Get Campaign |  |
| 135 | PATCH | N/A | /api/v1/donations/campaigns/{campaign_id} | donations | Update Campaign |  |
| 136 | DELETE | N/A | /api/v1/donations/campaigns/{campaign_id} | donations | Delete Campaign |  |
| 137 | POST | N/A | /api/v1/donations/checkout | donations | Initiate Donation Checkout |  |
| 138 | GET | N/A | /api/v1/donations/donors | donations | List Donors |  |
| 139 | POST | N/A | /api/v1/donations/donors/bulk/delete | donations | Bulk Delete Donors |  |
| 140 | GET | N/A | /api/v1/donations/donors/me | donations | Get My Donor Profile |  |
| 141 | PUT | N/A | /api/v1/donations/donors/{donor_id} | donations | Update Donor |  |
| 142 | DELETE | N/A | /api/v1/donations/donors/{donor_id} | donations | Soft Delete Donor |  |
| 143 | GET | N/A | /api/v1/donations/history | donations | Get Donation History |  |
| 144 | POST | N/A | /api/v1/donations/recurring | donations | Create Recurring Subscription |  |
| 145 | GET | N/A | /api/v1/donations/recurring | donations | List My Recurring Subscriptions |  |
| 146 | DELETE | N/A | /api/v1/donations/recurring/{subscription_id} | donations | Cancel Recurring Subscription |  |
| 147 | POST | N/A | /api/v1/donations/register | donations | Register Donor |  |
| 148 | POST | N/A | /api/v1/donations/sponsorships | donations | Create Sponsorship |  |
| 149 | GET | N/A | /api/v1/donations/sponsorships | donations | List All Sponsorships |  |
| 150 | GET | N/A | /api/v1/donations/sponsorships/my | donations | List My Sponsorships |  |
| 151 | GET | N/A | /api/v1/donations/sponsorships/{sponsorship_id} | donations | Get Sponsorship |  |
| 152 | PATCH | N/A | /api/v1/donations/sponsorships/{sponsorship_id}/status | donations | Update Sponsorship Status |  |
| 153 | POST | N/A | /api/v1/donations/verify | donations | Verify Donation Checkout |  |
| 154 | GET | N/A | /api/v1/donations/{donation_id}/receipt | donations | Get Donation Receipt |  |
| 155 | POST | N/A | /api/v1/donations/{donation_id}/reconcile | donations | Reconcile Donation |  |
| 156 | PATCH | N/A | /api/v1/donations/{donation_id}/status | donations | Update Donation Status |  |
| 157 | GET | N/A | /api/v1/finance/account-balances | finance | Get Account Balances |  |
| 158 | POST | N/A | /api/v1/finance/accounts | finance | Create Account |  |
| 159 | GET | N/A | /api/v1/finance/accounts | finance | List Accounts |  |
| 160 | POST | N/A | /api/v1/finance/accounts/bulk/delete | finance | Bulk Delete Accounts |  |
| 161 | GET | N/A | /api/v1/finance/accounts/{account_id} | finance | Get Account |  |
| 162 | PUT | N/A | /api/v1/finance/accounts/{account_id} | finance | Update Account |  |
| 163 | DELETE | N/A | /api/v1/finance/accounts/{account_id} | finance | Delete Account |  |
| 164 | POST | N/A | /api/v1/finance/budgets | finance | Create Budget |  |
| 165 | GET | N/A | /api/v1/finance/budgets | finance | List Budgets |  |
| 166 | GET | N/A | /api/v1/finance/budgets/{budget_id} | finance | Get Budget |  |
| 167 | DELETE | N/A | /api/v1/finance/budgets/{budget_id} | finance | Delete Budget |  |
| 168 | POST | N/A | /api/v1/finance/budgets/{budget_id}/items | finance | Add Budget Item |  |
| 169 | GET | N/A | /api/v1/finance/pnl | finance | Get Pnl |  |
| 170 | POST | N/A | /api/v1/finance/reconcile/donations | finance | Reconcile Donations |  |
| 171 | GET | N/A | /api/v1/finance/reconcile/summary | finance | Get Reconciliation Summary |  |
| 172 | POST | N/A | /api/v1/finance/recurring | finance | Create Recurring |  |
| 173 | GET | N/A | /api/v1/finance/recurring | finance | List Recurring |  |
| 174 | DELETE | N/A | /api/v1/finance/recurring/{rtx_id} | finance | Delete Recurring |  |
| 175 | GET | N/A | /api/v1/finance/summary | finance | Get Finance Summary |  |
| 176 | POST | N/A | /api/v1/finance/transactions | finance | Create Transaction |  |
| 177 | GET | N/A | /api/v1/finance/transactions | finance | List Transactions |  |
| 178 | POST | N/A | /api/v1/finance/transactions/bulk/delete | finance | Bulk Delete Transactions |  |
| 179 | GET | N/A | /api/v1/finance/transactions/{tx_id} | finance | Get Transaction |  |
| 180 | DELETE | N/A | /api/v1/finance/transactions/{tx_id} | finance | Delete Transaction |  |
| 181 | PATCH | N/A | /api/v1/finance/transactions/{tx_id}/status | finance | Update Transaction Status |  |
| 182 | POST | N/A | /api/v1/fleet/bulk/delete | fleet | Bulk Delete Vehicles |  |
| 183 | POST | N/A | /api/v1/fleet/bulk/status-update | fleet | Bulk Update Vehicle Status |  |
| 184 | POST | N/A | /api/v1/fleet/equipment | fleet | Checkout Equipment |  |
| 185 | GET | N/A | /api/v1/fleet/equipment | fleet | List Equipment Checkouts |  |
| 186 | GET | N/A | /api/v1/fleet/equipment/{checkout_id} | fleet | Get Equipment Checkout |  |
| 187 | POST | N/A | /api/v1/fleet/equipment/{checkout_id}/return | fleet | Return Equipment |  |
| 188 | GET | N/A | /api/v1/fleet/fuel/{log_id} | fleet | Get Fuel Log |  |
| 189 | POST | N/A | /api/v1/fleet/maintenance | fleet | Log Maintenance |  |
| 190 | POST | N/A | /api/v1/fleet/vehicles | fleet | Create Vehicle |  |
| 191 | GET | N/A | /api/v1/fleet/vehicles | fleet | List Vehicles |  |
| 192 | GET | N/A | /api/v1/fleet/vehicles/{vehicle_id} | fleet | Get Vehicle |  |
| 193 | PUT | N/A | /api/v1/fleet/vehicles/{vehicle_id} | fleet | Update Vehicle |  |
| 194 | DELETE | N/A | /api/v1/fleet/vehicles/{vehicle_id} | fleet | Soft Delete Vehicle |  |
| 195 | POST | N/A | /api/v1/fleet/vehicles/{vehicle_id}/fuel | fleet | Log Fuel |  |
| 196 | GET | N/A | /api/v1/fleet/vehicles/{vehicle_id}/fuel | fleet | List Fuel Logs |  |
| 197 | GET | N/A | /api/v1/fleet/vehicles/{vehicle_id}/maintenance | fleet | List Maintenance |  |
| 198 | PATCH | N/A | /api/v1/fleet/vehicles/{vehicle_id}/status | fleet | Update Vehicle Status |  |
| 199 | GET | N/A | /api/v1/fosters | fosters | List Profiles |  |
| 200 | DELETE | N/A | /api/v1/fosters/admin/fosters/{profile_id} | fosters | Soft Delete Profile |  |
| 201 | POST | N/A | /api/v1/fosters/apply | fosters | Apply To Foster |  |
| 202 | POST | N/A | /api/v1/fosters/bulk/delete | fosters | Bulk Delete Profiles |  |
| 203 | POST | N/A | /api/v1/fosters/placements/{placement_id}/convert-to-adopt | fosters | Convert To Adopt |  |
| 204 | POST | N/A | /api/v1/fosters/placements/{placement_id}/progress | fosters | Log Progress |  |
| 205 | GET | N/A | /api/v1/fosters/placements/{placement_id}/progress | fosters | Get Progress Logs |  |
| 206 | POST | N/A | /api/v1/fosters/placements/{placement_id}/return | fosters | Return Dog |  |
| 207 | POST | N/A | /api/v1/fosters/placements/{placement_id}/supplies | fosters | Log Supply Dispatch |  |
| 208 | GET | N/A | /api/v1/fosters/placements/{placement_id}/supplies | fosters | List Supply Dispatches |  |
| 209 | PUT | N/A | /api/v1/fosters/{profile_id} | fosters | Update Profile |  |
| 210 | DELETE | N/A | /api/v1/fosters/{profile_id} | fosters | Soft Delete Profile |  |
| 211 | POST | N/A | /api/v1/fosters/{profile_id}/placements | fosters | Place Dog |  |
| 212 | POST | N/A | /api/v1/grievance | grievance | Submit Complaint |  |
| 213 | GET | N/A | /api/v1/grievance | grievance | List Tickets |  |
| 214 | POST | N/A | /api/v1/grievance/bulk/delete | grievance | Bulk Delete Tickets |  |
| 215 | POST | N/A | /api/v1/grievance/bulk/status | grievance | Bulk Update Ticket Status |  |
| 216 | GET | N/A | /api/v1/grievance/feedback | grievance | List Feedback |  |
| 217 | POST | N/A | /api/v1/grievance/feedback | grievance | Submit Feedback |  |
| 218 | POST | N/A | /api/v1/grievance/feedback/bulk/delete | grievance | Bulk Delete Feedback |  |
| 219 | DELETE | N/A | /api/v1/grievance/feedback/{feedback_id} | grievance | Soft Delete Feedback |  |
| 220 | GET | N/A | /api/v1/grievance/{ticket_id} | grievance | Get Ticket |  |
| 221 | PUT | N/A | /api/v1/grievance/{ticket_id} | grievance | Update Ticket |  |
| 222 | DELETE | N/A | /api/v1/grievance/{ticket_id} | grievance | Soft Delete Ticket |  |
| 223 | POST | N/A | /api/v1/grievance/{ticket_id}/assign | grievance | Assign Ticket |  |
| 224 | POST | N/A | /api/v1/grievance/{ticket_id}/comments | grievance | Add Comment |  |
| 225 | GET | N/A | /api/v1/grievance/{ticket_id}/comments | grievance | List Comments |  |
| 226 | POST | N/A | /api/v1/grievance/{ticket_id}/escalate | grievance | Escalate Ticket |  |
| 227 | PATCH | N/A | /api/v1/grievance/{ticket_id}/status | grievance | Update Ticket Status |  |
| 228 | POST | N/A | /api/v1/inventory/items | inventory | Create Item |  |
| 229 | GET | N/A | /api/v1/inventory/items | inventory | List Items |  |
| 230 | POST | N/A | /api/v1/inventory/items/bulk/delete | inventory | Bulk Delete Items |  |
| 231 | GET | N/A | /api/v1/inventory/items/{item_id} | inventory | Get Item |  |
| 232 | DELETE | N/A | /api/v1/inventory/items/{item_id} | inventory | Delete Item |  |
| 233 | GET | N/A | /api/v1/inventory/items/{item_id}/movements | inventory | List Movements |  |
| 234 | POST | N/A | /api/v1/inventory/movements | inventory | Record Movement |  |
| 235 | POST | N/A | /api/v1/inventory/requisitions | inventory | Create Requisition |  |
| 236 | GET | N/A | /api/v1/inventory/requisitions | inventory | List Requisitions |  |
| 237 | POST | N/A | /api/v1/inventory/requisitions/bulk/status | inventory | Bulk Update Requisition Status |  |
| 238 | PUT | N/A | /api/v1/inventory/requisitions/{req_id}/status | inventory | Update Requisition Status |  |
| 239 | POST | N/A | /api/v1/lost-found/found | lost-found | Report Found Pet |  |
| 240 | GET | N/A | /api/v1/lost-found/found | lost-found | List Found Reports |  |
| 241 | POST | N/A | /api/v1/lost-found/found/bulk/delete | lost-found | Bulk Delete Found Reports |  |
| 242 | GET | N/A | /api/v1/lost-found/found/{report_id} | lost-found | Get Found Report |  |
| 243 | DELETE | N/A | /api/v1/lost-found/found/{report_id} | lost-found | Delete Found Report |  |
| 244 | GET | N/A | /api/v1/lost-found/found/{report_id}/matches | lost-found | Get Matches For Found |  |
| 245 | POST | N/A | /api/v1/lost-found/lost | lost-found | Report Lost Pet |  |
| 246 | GET | N/A | /api/v1/lost-found/lost | lost-found | List Lost Reports |  |
| 247 | POST | N/A | /api/v1/lost-found/lost/bulk/delete | lost-found | Bulk Delete Lost Reports |  |
| 248 | GET | N/A | /api/v1/lost-found/lost/{report_id} | lost-found | Get Lost Report |  |
| 249 | DELETE | N/A | /api/v1/lost-found/lost/{report_id} | lost-found | Delete Lost Report |  |
| 250 | POST | N/A | /api/v1/lost-found/lost/{report_id}/broadcast | lost-found | Broadcast Lost Pet Alert |  |
| 251 | GET | N/A | /api/v1/lost-found/lost/{report_id}/matches | lost-found | Get Matches For Lost |  |
| 252 | POST | N/A | /api/v1/lost-found/matches/{match_id}/claim | lost-found | Submit Ownership Claim |  |
| 253 | POST | N/A | /api/v1/lost-found/matches/{match_id}/claim/review | lost-found | Review Ownership Claim |  |
| 254 | POST | N/A | /api/v1/lost-found/matches/{match_id}/resolve | lost-found | Resolve Match |  |
| 255 | GET | N/A | /api/v1/lost-found/reunion-stories | lost-found | Get Reunion Stories |  |
| 256 | GET | N/A | /api/v1/lost-found/stories | lost-found | Get Reunion Stories |  |
| 257 | POST | N/A | /api/v1/medical/administrations | medical | Log Medication Administration |  |
| 258 | POST | N/A | /api/v1/medical/bulk/delete | medical | Bulk Delete Entities |  |
| 259 | POST | N/A | /api/v1/medical/bulk/prescriptions/status | medical | Bulk Update Prescription Status |  |
| 260 | POST | N/A | /api/v1/medical/clearance/{dog_id} | medical | Authorize Adoption Clearance |  |
| 261 | GET | N/A | /api/v1/medical/clearances/dogs/{dog_id} | medical | Get Dog Clearances |  |
| 262 | GET | N/A | /api/v1/medical/dogs/{dog_id}/administrations | medical | Get Dog Administrations |  |
| 263 | GET | N/A | /api/v1/medical/dogs/{dog_id}/history | medical | Get Medical History |  |
| 264 | POST | N/A | /api/v1/medical/exams | medical | Perform Clinical Exam |  |
| 265 | GET | N/A | /api/v1/medical/exams | medical | List Exams |  |
| 266 | POST | N/A | /api/v1/medical/prescriptions | medical | Prescribe Medication |  |
| 267 | GET | N/A | /api/v1/medical/prescriptions | medical | List Prescriptions |  |
| 268 | PUT | N/A | /api/v1/medical/prescriptions/{prescription_id} | medical | Update Prescription |  |
| 269 | GET | N/A | /api/v1/medical/prescriptions/{prescription_id}/administrations | medical | Get Prescription Administrations |  |
| 270 | PATCH | N/A | /api/v1/medical/prescriptions/{prescription_id}/status | medical | Update Prescription Status |  |
| 271 | POST | N/A | /api/v1/medical/treatments | medical | Record Treatment |  |
| 272 | GET | N/A | /api/v1/medical/treatments | medical | List Treatments |  |
| 273 | POST | N/A | /api/v1/medical/vaccinations | medical | Administer Vaccine |  |
| 274 | GET | N/A | /api/v1/medical/vaccinations | medical | List Vaccinations |  |
| 275 | POST | N/A | /api/v1/medical/vaccine-protocols | medical | Create Vaccine Protocol |  |
| 276 | GET | N/A | /api/v1/medical/vaccine-protocols | medical | List Vaccine Protocols |  |
| 277 | DELETE | N/A | /api/v1/medical/{entity_type}/{entity_id} | medical | Soft Delete Entity |  |
| 278 | GET | N/A | /api/v1/notifications | notifications | List Notifications |  |
| 279 | POST | N/A | /api/v1/notifications/broadcast | notifications | Broadcast Notification |  |
| 280 | POST | N/A | /api/v1/notifications/bulk/delete | notifications | Bulk Delete Notifications |  |
| 281 | GET | N/A | /api/v1/notifications/preferences | notifications | Get Preferences |  |
| 282 | PUT | N/A | /api/v1/notifications/preferences | notifications | Update Preferences |  |
| 283 | PUT | N/A | /api/v1/notifications/read-all | notifications | Mark All Read |  |
| 284 | POST | N/A | /api/v1/notifications/send | notifications | Send Notification |  |
| 285 | GET | N/A | /api/v1/notifications/unread-count | notifications | Unread Count |  |
| 286 | DELETE | N/A | /api/v1/notifications/{notification_id} | notifications | Delete Notification |  |
| 287 | PUT | N/A | /api/v1/notifications/{notification_id}/read | notifications | Mark Read |  |
| 288 | POST | N/A | /api/v1/portal/admin/blog | portal | Create Blog |  |
| 289 | GET | N/A | /api/v1/portal/admin/blog | portal | Admin List Blogs |  |
| 290 | POST | N/A | /api/v1/portal/admin/blog/bulk/delete | portal | Bulk Delete Blogs |  |
| 291 | POST | N/A | /api/v1/portal/admin/blog/bulk/status | portal | Bulk Update Blog Status |  |
| 292 | PUT | N/A | /api/v1/portal/admin/blog/{post_id} | portal | Update Blog |  |
| 293 | DELETE | N/A | /api/v1/portal/admin/blog/{post_id} | portal | Soft Delete Blog |  |
| 294 | GET | N/A | /api/v1/portal/admin/cms/pages | portal | List Admin Cms Pages |  |
| 295 | GET | N/A | /api/v1/portal/admin/cms/pages/{slug} | portal | Get Admin Cms Page |  |
| 296 | PUT | N/A | /api/v1/portal/admin/cms/pages/{slug} | portal | Update Admin Cms Page |  |
| 297 | POST | N/A | /api/v1/portal/admin/cms/pages/{slug}/discard | portal | Discard Admin Cms Page |  |
| 298 | POST | N/A | /api/v1/portal/admin/cms/pages/{slug}/publish | portal | Publish Admin Cms Page |  |
| 299 | POST | N/A | /api/v1/portal/admin/contact | portal | Create Contact |  |
| 300 | PUT | N/A | /api/v1/portal/admin/contact/{location_id} | portal | Update Contact |  |
| 301 | POST | N/A | /api/v1/portal/admin/faq | portal | Create Faq |  |
| 302 | GET | N/A | /api/v1/portal/admin/faq | portal | Admin List Faqs |  |
| 303 | POST | N/A | /api/v1/portal/admin/faq/bulk/delete | portal | Bulk Delete Faqs |  |
| 304 | POST | N/A | /api/v1/portal/admin/faq/bulk/status | portal | Bulk Update Faq Status |  |
| 305 | PUT | N/A | /api/v1/portal/admin/faq/{entry_id} | portal | Update Faq |  |
| 306 | DELETE | N/A | /api/v1/portal/admin/faq/{entry_id} | portal | Soft Delete Faq |  |
| 307 | POST | N/A | /api/v1/portal/admin/legal | portal | Create Legal Doc |  |
| 308 | GET | N/A | /api/v1/portal/admin/legal | portal | Admin List Legal Docs |  |
| 309 | PUT | N/A | /api/v1/portal/admin/legal/{doc_id} | portal | Update Legal Doc |  |
| 310 | DELETE | N/A | /api/v1/portal/admin/legal/{doc_id} | portal | Soft Delete Legal Doc |  |
| 311 | GET | N/A | /api/v1/portal/admin/settings | portal | List Settings |  |
| 312 | PUT | N/A | /api/v1/portal/admin/settings/{key} | portal | Upsert Setting |  |
| 313 | POST | N/A | /api/v1/portal/admin/success-stories | portal | Create Story |  |
| 314 | GET | N/A | /api/v1/portal/admin/success-stories | portal | Admin List Stories |  |
| 315 | POST | N/A | /api/v1/portal/admin/success-stories/bulk/delete | portal | Bulk Delete Stories |  |
| 316 | POST | N/A | /api/v1/portal/admin/success-stories/bulk/status | portal | Bulk Update Story Status |  |
| 317 | PUT | N/A | /api/v1/portal/admin/success-stories/{story_id} | portal | Update Story |  |
| 318 | DELETE | N/A | /api/v1/portal/admin/success-stories/{story_id} | portal | Soft Delete Story |  |
| 319 | POST | N/A | /api/v1/portal/admin/urgent-alerts | portal | Create Urgent Alert |  |
| 320 | GET | N/A | /api/v1/portal/admin/urgent-alerts | portal | Admin List Urgent Alerts |  |
| 321 | PUT | N/A | /api/v1/portal/admin/urgent-alerts/{alert_id} | portal | Update Urgent Alert |  |
| 322 | DELETE | N/A | /api/v1/portal/admin/urgent-alerts/{alert_id} | portal | Soft Delete Urgent Alert |  |
| 323 | POST | N/A | /api/v1/portal/admin/veterinary-network | portal | Create Vet |  |
| 324 | PUT | N/A | /api/v1/portal/admin/veterinary-network/{partner_id} | portal | Update Vet |  |
| 325 | GET | N/A | /api/v1/portal/blog | portal | List Published Blog |  |
| 326 | GET | N/A | /api/v1/portal/blog/slug/{slug} | portal | Get Blog By Slug |  |
| 327 | GET | N/A | /api/v1/portal/cms/pages/{slug} | portal | Get Public Cms Page |  |
| 328 | GET | N/A | /api/v1/portal/contact | portal | List Contact Locations |  |
| 329 | POST | N/A | /api/v1/portal/contact | portal | Submit Contact Message |  |
| 330 | GET | N/A | /api/v1/portal/faq | portal | List Faq |  |
| 331 | GET | N/A | /api/v1/portal/legal | portal | List Published Legal Docs |  |
| 332 | GET | N/A | /api/v1/portal/legal/{slug} | portal | Get Published Legal Doc |  |
| 333 | GET | N/A | /api/v1/portal/me/dashboard | portal | Get User Dashboard |  |
| 334 | POST | N/A | /api/v1/portal/newsletter/subscribe | portal | Subscribe Newsletter |  |
| 335 | GET | N/A | /api/v1/portal/stats | portal | Get Hero Stats |  |
| 336 | GET | N/A | /api/v1/portal/success-stories | portal | List Published Stories |  |
| 337 | GET | N/A | /api/v1/portal/success-stories/{story_id} | portal | Get Published Story |  |
| 338 | GET | N/A | /api/v1/portal/transparency | portal | Get Transparency Stats |  |
| 339 | GET | N/A | /api/v1/portal/urgent-alerts | portal | List Active Urgent Alerts |  |
| 340 | GET | N/A | /api/v1/portal/veterinary-network | portal | List Veterinary Partners |  |
| 341 | POST | N/A | /api/v1/public/rescue/media-upload-url | public-rescue | Request Rescue Media Upload Url |  |
| 342 | POST | N/A | /api/v1/public/rescue/report | public-rescue | Public Report Incident |  |
| 343 | GET | N/A | /api/v1/reports/download/{filename} | reports | Download Report |  |
| 344 | GET | N/A | /api/v1/reports/formats | reports | List Report Formats |  |
| 345 | POST | N/A | /api/v1/reports/generate | reports | Generate Report |  |
| 346 | GET | N/A | /api/v1/reports/types | reports | List Report Types |  |
| 347 | GET | N/A | /api/v1/rescue | rescue | List Requests |  |
| 348 | GET | N/A | /api/v1/rescue-centres | rescue-centres | List Rescue Centres |  |
| 349 | POST | N/A | /api/v1/rescue-centres | rescue-centres | Create Rescue Centre |  |
| 350 | POST | N/A | /api/v1/rescue-centres/bulk/delete | rescue-centres | Bulk Delete Rescue Centres |  |
| 351 | POST | N/A | /api/v1/rescue-centres/bulk/status | rescue-centres | Bulk Update Rescue Centre Status |  |
| 352 | GET | N/A | /api/v1/rescue-centres/{facility_id} | rescue-centres | Get Rescue Centre |  |
| 353 | PUT | N/A | /api/v1/rescue-centres/{facility_id} | rescue-centres | Update Rescue Centre |  |
| 354 | DELETE | N/A | /api/v1/rescue-centres/{facility_id} | rescue-centres | Delete Rescue Centre |  |
| 355 | PUT | N/A | /api/v1/rescue-centres/{facility_id}/status | rescue-centres | Update Rescue Centre Status |  |
| 356 | POST | N/A | /api/v1/rescue/bulk/delete | rescue | Bulk Delete Rescue Requests |  |
| 357 | POST | N/A | /api/v1/rescue/bulk/status-update | rescue | Bulk Update Rescue Status |  |
| 358 | PATCH | N/A | /api/v1/rescue/dispatch/{dispatch_id} | rescue | Update Dispatch |  |
| 359 | DELETE | N/A | /api/v1/rescue/dispatch/{dispatch_id} | rescue | Delete Dispatch |  |
| 360 | GET | N/A | /api/v1/rescue/dispatches | rescue | List Dispatches |  |
| 361 | PATCH | N/A | /api/v1/rescue/dispatches/{dispatch_id} | rescue | Update Dispatch |  |
| 362 | DELETE | N/A | /api/v1/rescue/dispatches/{dispatch_id} | rescue | Delete Dispatch |  |
| 363 | POST | N/A | /api/v1/rescue/media-upload-url | rescue | Request Rescue Media Upload Url |  |
| 364 | POST | N/A | /api/v1/rescue/report | rescue | Report Incident |  |
| 365 | GET | N/A | /api/v1/rescue/status | rescue | Get Public Status |  |
| 366 | GET | N/A | /api/v1/rescue/{request_id} | rescue | Get Request |  |
| 367 | DELETE | N/A | /api/v1/rescue/{request_id} | rescue | Soft Delete Request |  |
| 368 | POST | N/A | /api/v1/rescue/{request_id}/admitted | rescue | Mark Admitted |  |
| 369 | POST | N/A | /api/v1/rescue/{request_id}/assign-coordinator | rescue | Assign Coordinator |  |
| 370 | POST | N/A | /api/v1/rescue/{request_id}/dispatch | rescue | Dispatch Team |  |
| 371 | POST | N/A | /api/v1/rescue/{request_id}/escalate | rescue | Escalate Rescue |  |
| 372 | POST | N/A | /api/v1/rescue/{request_id}/fail | rescue | Fail Rescue |  |
| 373 | POST | N/A | /api/v1/rescue/{request_id}/located | rescue | Mark Located |  |
| 374 | POST | N/A | /api/v1/rescue/{request_id}/secured | rescue | Mark Rescued |  |
| 375 | POST | N/A | /api/v1/rescue/{request_id}/verify | rescue | Verify Request |  |
| 376 | GET | N/A | /api/v1/settings/business-rules | settings | List Business Rules |  |
| 377 | POST | N/A | /api/v1/settings/business-rules | settings | Create Business Rule |  |
| 378 | DELETE | N/A | /api/v1/settings/business-rules/{rule_id} | settings | Delete Business Rule |  |
| 379 | GET | N/A | /api/v1/settings/business-rules/{rule_key} | settings | Get Business Rule |  |
| 380 | PUT | N/A | /api/v1/settings/business-rules/{rule_key} | settings | Update Business Rule |  |
| 381 | GET | N/A | /api/v1/settings/email | settings | Get Email Settings |  |
| 382 | GET | N/A | /api/v1/settings/general | settings | Get General Settings |  |
| 383 | GET | N/A | /api/v1/settings/password-policy | settings | Get Password Policy |  |
| 384 | PUT | N/A | /api/v1/settings/password-policy | settings | Update Password Policy |  |
| 385 | GET | N/A | /api/v1/settings/public-content | settings | Get Public Content |  |
| 386 | PUT | N/A | /api/v1/settings/public-content | settings | Update Public Content |  |
| 387 | GET | N/A | /api/v1/settings/storage | settings | Get Storage Settings |  |
| 388 | GET | N/A | /api/v1/settings/system | settings | List Settings |  |
| 389 | POST | N/A | /api/v1/settings/system | settings | Create Setting |  |
| 390 | GET | N/A | /api/v1/settings/system/{key} | settings | Get Setting |  |
| 391 | PUT | N/A | /api/v1/settings/system/{key} | settings | Update Setting |  |
| 392 | DELETE | N/A | /api/v1/settings/system/{setting_id} | settings | Delete Setting |  |
| 393 | POST | N/A | /api/v1/shelter/care-logs | shelter | Submit Daily Care Log |  |
| 394 | GET | N/A | /api/v1/shelter/dogs/{dog_id}/care-logs | shelter | List Care Logs |  |
| 395 | POST | N/A | /api/v1/shelter/facilities | shelter | Create Facility |  |
| 396 | GET | N/A | /api/v1/shelter/facilities | shelter | List Facilities |  |
| 397 | POST | N/A | /api/v1/shelter/facilities/bulk/delete | shelter | Bulk Delete Facilities |  |
| 398 | POST | N/A | /api/v1/shelter/facilities/bulk/status | shelter | Bulk Update Facility Status |  |
| 399 | GET | N/A | /api/v1/shelter/facilities/{facility_id} | shelter | Get Facility |  |
| 400 | PUT | N/A | /api/v1/shelter/facilities/{facility_id} | shelter | Update Facility |  |
| 401 | DELETE | N/A | /api/v1/shelter/facilities/{facility_id} | shelter | Delete Facility |  |
| 402 | POST | N/A | /api/v1/shelter/facilities/{facility_id}/sections | shelter | Create Section |  |
| 403 | GET | N/A | /api/v1/shelter/facilities/{facility_id}/sections | shelter | List Sections |  |
| 404 | PUT | N/A | /api/v1/shelter/facilities/{facility_id}/status | shelter | Update Facility Status |  |
| 405 | PATCH | N/A | /api/v1/shelter/kennels/{kennel_id}/assign/{dog_id} | shelter | Assign Dog To Kennel |  |
| 406 | POST | N/A | /api/v1/shelter/kennels/{kennel_id}/assign/{dog_id} | shelter | Assign Dog To Kennel |  |
| 407 | POST | N/A | /api/v1/shelter/kennels/{kennel_id}/cleaning-logs | shelter | Log Kennel Cleaning |  |
| 408 | GET | N/A | /api/v1/shelter/kennels/{kennel_id}/cleaning-logs | shelter | List Kennel Cleaning Logs |  |
| 409 | PUT | N/A | /api/v1/shelter/kennels/{kennel_id}/sanitation | shelter | Update Kennel Sanitation |  |
| 410 | POST | N/A | /api/v1/shelter/sections/{section_id}/kennels | shelter | Create Kennel |  |
| 411 | GET | N/A | /api/v1/shelter/sections/{section_id}/kennels | shelter | List Kennels |  |
| 412 | POST | N/A | /api/v1/shelter/transfers | shelter | Request Transfer |  |
| 413 | GET | N/A | /api/v1/shelter/transfers | shelter | List Transfers |  |
| 414 | GET | N/A | /api/v1/shelter/transfers/{transfer_id} | shelter | Get Transfer |  |
| 415 | POST | N/A | /api/v1/shelter/transfers/{transfer_id}/confirm-receiver | shelter | Confirm Transfer Receiver |  |
| 416 | POST | N/A | /api/v1/shelter/transfers/{transfer_id}/confirm-sender | shelter | Confirm Transfer Sender |  |
| 417 | GET | N/A | /api/v1/storage | storage | List Files |  |
| 418 | POST | N/A | /api/v1/storage/bulk/delete | storage | Bulk Delete Files |  |
| 419 | GET | N/A | /api/v1/storage/entity/{entity_type}/{entity_id} | storage | List Files By Entity |  |
| 420 | POST | N/A | /api/v1/storage/upload-url | storage | Request Upload Url |  |
| 421 | GET | N/A | /api/v1/storage/{file_id} | storage | Get File |  |
| 422 | DELETE | N/A | /api/v1/storage/{file_id} | storage | Delete File |  |
| 423 | PUT | N/A | /api/v1/storage/{file_id}/confirm | storage | Confirm Upload |  |
| 424 | GET | N/A | /api/v1/storage/{file_id}/download-url | storage | Get Download Url |  |
| 425 | GET | N/A | /api/v1/volunteers | volunteers | List Profiles |  |
| 426 | POST | N/A | /api/v1/volunteers/apply | volunteers | Apply To Volunteer |  |
| 427 | POST | N/A | /api/v1/volunteers/attendance/{attendance_id}/check-in | volunteers | Check In |  |
| 428 | POST | N/A | /api/v1/volunteers/attendance/{attendance_id}/check-out | volunteers | Check Out |  |
| 429 | POST | N/A | /api/v1/volunteers/bulk/delete | volunteers | Bulk Delete Profiles |  |
| 430 | POST | N/A | /api/v1/volunteers/bulk/status | volunteers | Bulk Update Profile Status |  |
| 431 | GET | N/A | /api/v1/volunteers/shifts | volunteers | List Shifts |  |
| 432 | POST | N/A | /api/v1/volunteers/shifts | volunteers | Create Shift |  |
| 433 | GET | N/A | /api/v1/volunteers/shifts/{shift_id}/attendance | volunteers | List Shift Attendance |  |
| 434 | POST | N/A | /api/v1/volunteers/shifts/{shift_id}/join | volunteers | Join Shift |  |
| 435 | PUT | N/A | /api/v1/volunteers/{profile_id} | volunteers | Update Profile |  |
| 436 | DELETE | N/A | /api/v1/volunteers/{profile_id} | volunteers | Soft Delete Profile |  |
| 437 | GET | N/A | /api/v1/volunteers/{profile_id} | volunteers | Get Profile |  |
| 438 | GET | N/A | /api/v1/volunteers/{profile_id}/certificate | volunteers | Issue Service Certificate |  |
| 439 | GET | N/A | /api/v1/volunteers/{profile_id}/service-summary | volunteers | Get Service Summary |  |
| 440 | GET | N/A | /health |  | Health |  |
| 441 | GET | N/A | /live |  | Live |  |
| 442 | GET | N/A | /ready |  | Ready |  |