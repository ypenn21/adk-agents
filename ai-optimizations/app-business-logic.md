# ORDERFLOW - AI Integration Explained

## The AI Brain of the System

ORDERFLOW uses AI (OpenAI or Trucube) as its "conversation interpreter" - it reads text messages and makes smart decisions. Here's what the AI actually does:

## 4 Main AI Functions

### 1. **Order Detection** (`analyzeOrderSummaryFromConversation`)
**What it does:** Reads the entire conversation and figures out if someone placed an order

**Example:**
```
Customer: "Hey can I get 2 burgers?"
Customer: "Actually make it 3"
Customer: "And add fries"
```

**AI extracts:**
- Items: 3 burgers, 1 fries
- Customer name (if mentioned)
- Pickup time
- Total price (matches items to menu)
- Special notes

**Smart features:**
- Looks at the WHOLE conversation history, not just one message
- Updates if customer changes their mind
- Matches "burger" to "Classic Burger" on the menu
- Calculates prices automatically

---

### 2. **Pickup Time Detection** (`detectPickupTimeFromConversation`)
**What it does:** Figures out WHEN the customer wants their food

**Handles different formats:**
- "3:30 PM" → exact time
- "in 30 minutes" → calculates from current time
- "half an hour" → converts to time
- "at 3:30" (without AM/PM) → makes intelligent guess

**Smart tracking:**
- Detects when pickup time changes during conversation
- Knows when restaurant proposes a time and customer confirms
- Converts everything to actual timestamps

---

### 3. **AI Suggested Responses** (`generateAISuggestedResponse`)
**What it does:** Writes reply suggestions for the restaurant manager

**Example scenario:**
```
Customer: "Can I get 2 burgers for pickup at 6pm?"

AI suggests: "Got it! 2 burgers ready at 6pm. See you then!"
```

**Rules it follows:**
- Only suggests when customer sent the last message (not after manager just replied)
- Keeps responses short (10-20 words)
- Sounds casual and human, not robotic
- Cached per order (doesn't regenerate the same suggestion repeatedly)

---

### 4. **Edge Case Handling** (`analyzeConditionalAIOutput`)
**What it does:** Handles weird or special requests that need custom logic

**Example:**
```
Customer: "Can I get a half sandwich?"
```

The menu doesn't have "half sandwich" - it's called "Lunch Special"

**AI automatically:**
- Recognizes the edge case
- Converts "half sandwich" → "Lunch special"
- Updates the order correctly

---

## How AI Integrates With the System

```
SMS arrives → Saved to database → AI automatically triggers → Analyzes conversation → Updates order → Dashboard refreshes in real-time
```

### Key Integration Points:

1. **Automatic Processing**
   - Every new SMS triggers AI analysis
   - In production mode, also runs on a timer (checks for new messages)

2. **Model Flexibility**
   - Can use OpenAI or Trucube
   - Set via `MODEL=OPENAI` or `MODEL=TRUCUBE` environment variable
   - All AI functions use the same model

3. **Prompt Engineering**
   - AI prompts stored in `server/utils.ts`
   - Functions in `server/aiFunctions.ts`
   - Easy to tweak AI behavior by updating prompts

4. **Caching & Performance**
   - Suggested responses are cached per order
   - Avoids redundant API calls
   - Saves money and speeds up responses

---

## Real-World Examples (From Corn On The Corner)

### Example 1: Simple Order with Pickup Time Negotiation

**Conversation (Sample Conversation 2):**
```
Customer: "Hey"
Customer: "1 Nashville grilled chicken spicy
1 fries
Azer Khan
810 pm"
Restaurant: "Does 8:40 work?"
Customer: "Ya"
```

**AI Processing:**
```
Message 1 ("Hey"):
→ AI: No order detected yet, just greeting

Message 2 (Order details):
→ AI detects order:
  - Items: 1 Nashville grilled chicken spicy, 1 fries
  - Customer: Azer Khan
  - Pickup: 8:10 PM
→ Dashboard shows: New order detected
→ Order summary auto-generated

Message 3 (Restaurant counter-offer):
→ AI updates: Pickup time → 8:40 PM (proposed)
→ Status: Pending customer confirmation

Message 4 ("Ya"):
→ AI confirms: Customer accepted 8:40 PM
→ Order status: Confirmed
→ Final order: $13.98 (Nashville chicken $9.99 + Fries $3.99)
```

---

### Example 2: Half Sandwich Edge Case (Must Reject)

**Conversation (Sample Conversation 3.5):**
```
Restaurant: "Corn On The Corner, This is our storefront location..."
Customer: "1/2 Nashville grilled chicken spicy
Azer Khan
630 pm"
Customer: "does it come with fries?"
Restaurant: "Hey sorry about that we can't do half grilled cheeses!"
```

**AI Processing:**
```
Message 1 (Auto-greeting):
→ AI: Template message, no order yet

Message 2 ("1/2 Nashville..."):
→ AI detects: Invalid item "1/2 Nashville grilled chicken spicy"
→ AI checks menu: "1/2 Nashville" NOT FOUND
→ ⚠️ Potential match: "Lunch special" ($6.99)
→ Status: Ambiguous - needs clarification

Message 3 ("does it come with fries?"):
→ AI: Customer asking question, still no valid order

Message 4 (Restaurant rejection):
→ AI: Restaurant explicitly rejected half sandwich request
→ AI sets: orderMade = FALSE
→ Dashboard shows: No order (inquiry only)
→ ❌ DO NOT hallucinate "half sandwich" item
```

**Critical: AI must NOT output:**
```json
❌ WRONG:
{
  "items": ["1x Half Nashville grilled chicken spicy: $4.99"]
}

✅ CORRECT:
{
  "orderMade": false,
  "items": []
}
```

---

### Example 3: Order Build-Up with Modifications

**Conversation (Sample Conversation 1):**
```
Customer: "1 Nashville Chicken
Azer Khan
845 pm"
Restaurant: "Got it does 8:55 work"
Customer: "does it come w fries?"
Customer: "and yes works"
Restaurant: "Yes"
Restaurant: "Grilled cheese or sliders?"
Customer: "grilled cheese"
Customer: "add fries please"
Restaurant: "No problem"
```

**AI Processing (Incremental):**
```
Step 1 - Initial order:
→ Items: [Nashville Chicken]
→ Customer: Azer Khan
→ Pickup: 8:45 PM (requested)

Step 2 - Time negotiation:
→ Restaurant proposes: 8:55 PM
→ Pickup: 8:55 PM (proposed)

Step 3 - Customer confirms:
→ "and yes works"
→ Pickup: 8:55 PM (CONFIRMED)

Step 4 - Customer adds grilled cheese:
→ Items: [Nashville Chicken, Grilled Cheese]

Step 5 - Customer adds fries:
→ "add fries please"
→ Items: [Nashville Chicken, Grilled Cheese, Fries]
→ Total: $19.97
→ Status: Complete and confirmed
```

**Key: AI must ACCUMULATE items, not REPLACE:**
```json
✅ CORRECT (all items):
{
  "items": [
    "Nashville Chicken: $8.99",
    "Grilled Cheese: $6.99",
    "Fries: $3.99"
  ],
  "total": 19.97
}

❌ WRONG (only last item):
{
  "items": ["Fries: $3.99"]
}
```

---

### Example 4: Complex Order with Combo Notation

**Conversation (Sample Conversation 7):**
```
Customer: "3 Nashville grilled cheese spicy (2 combo)
1 cheese steak sandwich
Azer khan
asap"
Restaurant: "Got it does 9:15 work?"
Customer: "Yes thx"
```

**AI Processing:**
```
Message 1 (Complex order):
→ AI parses:
  - 3x Nashville grilled cheese spicy
  - (2 combo) = 2 of the 3 are combo upgrades
  - 1x Cheese steak sandwich
  - Customer: Azer Khan
  - Pickup: ASAP (needs confirmation)

→ AI calculates:
  - Base: 3 × $6.99 = $20.97 (Nashville grilled cheese)
  - Upgrades: 2 × $1.99 = $3.98 (combo upgrades)
  - Add: 1 × $8.99 = $8.99 (cheese steak)
  - Total: $33.94

Message 2 (Restaurant proposes time):
→ Pickup: 9:15 PM (proposed)

Message 3 ("Yes thx"):
→ Pickup: 9:15 PM (CONFIRMED)
→ Order finalized: $33.94
```

**Key: AI must parse combo notation:**
```
"(2 combo)" means:
- 2 out of 3 items upgraded to combo
- Combo adds $1.99 per item
- Track as separate line item
```

---

### Example 5: Inquiry Detection (NOT an Order)

**Conversation (Sample Conversation 4):**
```
Restaurant: "Corn On The Corner, This is our storefront location..."
Customer: "Wait time on chicken caesar wrap?"
Restaurant: "An hour currently"
```

**AI Processing:**
```
Message 1 (Auto-greeting):
→ AI: Template, no order

Message 2 (Wait time inquiry):
→ AI detects: Question about "wait time"
→ AI identifies: This is INQUIRY, not ORDER
→ orderMade: FALSE
→ Dashboard: No order created

Message 3 (Restaurant answers):
→ AI: Conversation ended without placing order
→ Final status: No order
```

**Key: AI must distinguish inquiry from order:**
```json
✅ CORRECT:
{
  "orderMade": false,
  "items": [],
  "inquiry": "Wait time on chicken caesar wrap"
}

❌ WRONG (false positive):
{
  "orderMade": true,
  "items": ["Chicken caesar wrap: $8.99"]
}
```

---

### Example 6: Order Modification After Confirmation

**Conversation (Sample Conversation 5):**
```
Customer: "Nashville grilled cheese spicy
Azer khan
asap"
Restaurant: "Got you does 5:10 work?"
Customer: "Yea"
Customer: "Hey"
Customer: "can you add
Crispy Cancun"
Restaurant: "Restaurant 'loved' Customer message"
```

**AI Processing:**
```
Initial order:
→ Items: [Nashville grilled cheese spicy]
→ Total: $6.99
→ Status: Confirmed for 5:10 PM

Modification detected:
→ Customer: "can you add Crispy Cancun"
→ AI updates items: [Nashville grilled cheese, Crispy Cancun]
→ AI recalculates: $6.99 + $8.99 = $15.98
→ Dashboard: Order updated
→ Restaurant reaction: "Loved" (confirmation)
```

**Key: Detect order modifications post-confirmation:**
```
Detection patterns:
- "add X"
- "can you add X"
- "also get X"
- "and X too"

Action:
→ Add to existing order
→ Update total
→ Alert restaurant of change
```

## The Intelligence

The AI isn't just pattern matching - it:
- **Understands context** (reads full conversation history)
- **Learns from corrections** (customer changes order)
- **Handles ambiguity** (guesses AM/PM, matches menu items)
- **Sounds human** (casual response style)
- **Adapts to edge cases** (half sandwich → lunch special)

Think of it as having a **smart assistant reading every customer text** and doing all the tedious work of extracting order details, so the restaurant manager just sees a clean summary and can respond quickly.

---

## Application Overview

### The Basic Idea

Instead of calling a restaurant to place an order, customers can just **send a text message**. The system uses AI to automatically understand what they want and helps the restaurant manage everything.

### How It Works (Step-by-Step)

1. **Customer texts the restaurant**
   - "Hi, I'd like 2 burgers and fries for pickup at 3pm"

2. **AI reads and understands the message**
   - Figures out what items they want
   - Detects quantities (2 burgers)
   - Finds the pickup time (3pm)
   - Matches items to menu prices

3. **Restaurant manager sees it on a dashboard**
   - Live conversation view (like iMessage)
   - Order summary automatically created
   - AI even suggests responses to send back

4. **Manager can reply instantly**
   - Click a suggested response or type their own
   - Message goes back to customer via text

### Key Benefits

- **Automated**: No manual order entry - AI does the hard work
- **Real-time**: Dashboard updates live as messages come in
- **Smart**: Understands things like "in 30 minutes" or "half sandwich"
- **Easy**: Restaurant staff just respond through a web dashboard

### Tech Stack

- Built with **React** (web dashboard) and **Node.js** (backend)
- Uses **OpenAI** or similar AI to read messages
- **Twilio** handles the actual text messaging
- **PostgreSQL** database stores orders and conversations

Think of it as **"iMessage meets AI assistant for restaurant orders"** - it makes ordering by text as easy as texting a friend.
