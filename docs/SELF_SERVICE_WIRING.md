# Self-Service Onboarding - Wiring Spec

## Goal
User goes from askboswell.com → paying customer → using Boswell with ZERO manual intervention.

## Current State

### ✅ Already Working
- `POST /v2/admin/create-tenant` - creates tenant + API key (requires GODMODE)
- `POST /v2/billing/webhook` - receives Stripe events
- `GET /api/extension/download?api_key=xxx` - generates .mcpb bundle
- Dashboard shell at `/` serves React app
- Stripe checkout session creation

### ❌ Not Connected
- Public registration (no auth required)
- Stripe webhook doesn't auto-provision tenant
- Dashboard doesn't show API key or download button
- No login/session for users

---

## The Wiring

### 0. Legal Agreement Checkbox

**Landing page signup form must include:**

```html
<label>
  <input type="checkbox" name="agree_terms" required />
  I agree to the <a href="/legal/terms">Terms of Service</a> 
  and <a href="/legal/privacy">Privacy Policy</a>
</label>
```

**Registration endpoint must verify:**

```python
agreed_to_terms = data.get('agreed_to_terms', False)
if not agreed_to_terms:
    return jsonify({'error': 'You must agree to the Terms of Service'}), 400
```

**Store consent timestamp:**

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP;
```

This is legally required before collecting any user data or processing payments.

---

### 1. Public Registration Endpoint

**File:** `auth/registration.py` (exists, needs modification)

**New endpoint:** `POST /v2/auth/register`

```python
@app.route('/v2/auth/register', methods=['POST'])
def register():
    """
    Public registration - no auth required.
    Creates user record, does NOT create tenant yet.
    Tenant created after successful Stripe payment.
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    # Validate
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    # Check if exists
    cur = get_cursor()
    cur.execute('SELECT id FROM users WHERE email = %s', (email,))
    if cur.fetchone():
        return jsonify({'error': 'Email already registered'}), 409
    
    # Hash password
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    # Create user (NOT tenant - that happens after payment)
    cur.execute('''
        INSERT INTO users (email, password_hash, created_at, status, terms_accepted_at)
        VALUES (%s, %s, NOW(), 'pending_payment', NOW())
        RETURNING id
    ''', (email, password_hash))
    user_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    
    # Create session token
    token = secrets.token_urlsafe(32)
    # Store in sessions table...
    
    return jsonify({
        'user_id': user_id,
        'status': 'pending_payment',
        'next': '/checkout'
    }), 201
```

### 2. Stripe Checkout with User ID

**File:** `billing/stripe_handler.py`

**Modify:** `POST /v2/billing/checkout`

```python
@billing_bp.route('/checkout', methods=['POST'])
@require_auth  # User must be logged in
def create_checkout():
    """
    Creates Stripe checkout session.
    Passes user_id in metadata so webhook knows who paid.
    """
    user_id = g.get('current_user_id')
    plan = request.json.get('plan', 'pro')
    
    price_id = {
        'pro': os.environ['STRIPE_PRICE_PRO'],
        'team': os.environ['STRIPE_PRICE_TEAM']
    }.get(plan)
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': 1}],
        mode='subscription',
        success_url='https://askboswell.com/dashboard?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://askboswell.com/pricing',
        metadata={
            'user_id': user_id,  # CRITICAL: ties payment to user
            'plan': plan
        }
    )
    
    return jsonify({'checkout_url': session.url})
```

### 3. Webhook Auto-Provisions Tenant

**File:** `billing/stripe_handler.py`

**Modify:** webhook handler for `checkout.session.completed`

```python
@billing_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ['STRIPE_WEBHOOK_SECRET']
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        plan = session['metadata']['plan']
        customer_id = session['customer']
        subscription_id = session['subscription']
        
        # AUTO-PROVISION TENANT
        cur = get_cursor()
        
        # Get user email for tenant name
        cur.execute('SELECT email FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        email = user['email']
        
        # Create tenant
        tenant_id = str(uuid.uuid4())
        cur.execute('''
            INSERT INTO tenants (id, name, created_at)
            VALUES (%s, %s, NOW())
        ''', (tenant_id, email))
        
        # Generate API key
        api_key = 'bos_' + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        cur.execute('''
            INSERT INTO api_keys (tenant_id, key_hash, created_at)
            VALUES (%s, %s, NOW())
        ''', (tenant_id, key_hash))
        
        # Create default branches
        for branch in ['command-center', 'work', 'personal', 'research']:
            cur.execute('''
                INSERT INTO branches (tenant_id, name, created_at)
                VALUES (%s, %s, NOW())
            ''', (tenant_id, branch))
        
        # Update user with tenant_id, subscription info, and STORE THE API KEY
        # We need to store the actual key (encrypted) so user can see it in dashboard
        cur.execute('''
            UPDATE users SET 
                tenant_id = %s,
                stripe_customer_id = %s,
                stripe_subscription_id = %s,
                plan = %s,
                status = 'active',
                api_key_display = %s  -- Store encrypted for display
            WHERE id = %s
        ''', (tenant_id, customer_id, subscription_id, plan, encrypt(api_key), user_id))
        
        conn.commit()
        cur.close()
        
        # Optionally send welcome email here
        
    return jsonify({'received': True})
```

### 4. Dashboard Shows API Key + Download

**File:** `static/src/views/Dashboard.tsx` (or similar)

**API endpoint needed:** `GET /v2/me`

```python
@app.route('/v2/me', methods=['GET'])
@require_auth
def get_me():
    """Returns current user's account info including API key."""
    user_id = g.get('current_user_id')
    
    cur = get_cursor()
    cur.execute('''
        SELECT email, tenant_id, plan, status, api_key_display, created_at
        FROM users WHERE id = %s
    ''', (user_id,))
    user = cur.fetchone()
    cur.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'email': user['email'],
        'tenant_id': user['tenant_id'],
        'plan': user['plan'],
        'status': user['status'],
        'api_key': decrypt(user['api_key_display']) if user['api_key_display'] else None,
        'member_since': user['created_at'].isoformat()
    })
```

**Dashboard React component:**

```tsx
function Dashboard() {
  const [user, setUser] = useState(null);
  const [copied, setCopied] = useState(false);
  
  useEffect(() => {
    fetch('/v2/me', { credentials: 'include' })
      .then(r => r.json())
      .then(setUser);
  }, []);
  
  if (!user) return <Loading />;
  
  if (user.status === 'pending_payment') {
    return <UpgradePrompt />;
  }
  
  const downloadUrl = `/api/extension/download?api_key=${user.api_key}`;
  
  return (
    <div>
      <h1>Welcome to Boswell</h1>
      
      <section>
        <h2>Your API Key</h2>
        <code>{user.api_key}</code>
        <button onClick={() => {
          navigator.clipboard.writeText(user.api_key);
          setCopied(true);
        }}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </section>
      
      <section>
        <h2>Install Boswell</h2>
        <a href={downloadUrl} className="button-primary">
          Download for Claude Desktop (.mcpb)
        </a>
        <p>Double-click the file to install. Restart Claude Desktop.</p>
      </section>
      
      <section>
        <h2>Quick Start</h2>
        <p>After installing, open Claude Desktop and say:</p>
        <code>Call boswell_startup</code>
      </section>
    </div>
  );
}
```

---

## Database Changes

**New table or columns needed:**

```sql
-- Add to users table (if not exists)
ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending_payment';
ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key_display TEXT; -- encrypted
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP; -- legal consent
```

---

## Flow Summary

```
1. User visits askboswell.com/signup
2. User checks "I agree to Terms of Service and Privacy Policy"
3. POST /v2/auth/register (email, password, agreed_to_terms=true)
   → Validates terms checkbox
   → Creates user with status='pending_payment', terms_accepted_at=NOW()
   → Returns session token
   
3. User redirected to pricing/checkout
4. POST /v2/billing/checkout (plan='pro')
   → Creates Stripe checkout session with user_id in metadata
   → Returns checkout URL
   
5. User completes Stripe payment
6. Stripe sends webhook to POST /v2/billing/webhook
   → Event: checkout.session.completed
   → Extracts user_id from metadata
   → Creates tenant
   → Generates API key
   → Creates default branches
   → Updates user: status='active', stores tenant_id + api_key
   
7. User redirected to /dashboard
8. GET /v2/me
   → Returns user info including API key
   
9. User clicks "Download for Claude Desktop"
10. GET /api/extension/download?api_key=bos_xxx
    → Returns personalized .mcpb bundle
    
11. User double-clicks .mcpb, installs, uses Boswell
```

---

## Files to Modify

| File | Change |
|------|--------|
| `auth/registration.py` | Add public POST /v2/auth/register with terms validation |
| `billing/stripe_handler.py` | Add user_id to checkout metadata |
| `billing/stripe_handler.py` | Auto-provision tenant on webhook |
| `app.py` | Add GET /v2/me endpoint |
| `static/src/views/Dashboard.tsx` | Show API key + download button |
| `schema_postgres.sql` | Add columns to users table (incl. terms_accepted_at) |
| `landing/src/app/signup/page.tsx` | Add terms checkbox to signup form |

---

## Legal Pages to Add

Add these routes to the landing site:

| Route | Content |
|-------|---------|
| `/legal/terms` | Terms of Service |
| `/legal/privacy` | Privacy Policy |
| `/legal/acceptable-use` | Acceptable Use Policy |
| `/legal/refund` | Refund Policy |
| `/legal/cancellation` | Cancellation Policy |
| `/legal/security` | Security Overview |

Source files in: `boswell-api-repo/docs/legal/`

Footer on all pages should link to Terms and Privacy at minimum.

---

## Environment Variables Required

Already set:
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_TEAM`

---

## Testing Checklist

1. [ ] Register new user (no GODMODE)
2. [ ] User status is 'pending_payment'
3. [ ] Create checkout session
4. [ ] Complete test payment (4242 4242 4242 4242)
5. [ ] Webhook fires, tenant auto-created
6. [ ] User status changes to 'active'
7. [ ] GET /v2/me returns API key
8. [ ] Download .mcpb works
9. [ ] Install in Claude Desktop
10. [ ] boswell_startup works

---

## Estimated Effort

- Legal checkbox + validation: 15 min
- Legal pages on landing site: 30 min
- Registration endpoint: 30 min
- Checkout metadata: 15 min
- Webhook auto-provision: 1 hour
- /v2/me endpoint: 30 min
- Dashboard UI: 1 hour
- Testing: 1 hour

**Total: ~5 hours**
