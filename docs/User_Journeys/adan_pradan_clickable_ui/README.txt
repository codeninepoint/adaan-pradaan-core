ADAN PRADAN CLICKABLE UI PROTOTYPE
=================================

START HERE
1. Extract adan_pradan_clickable_html.zip to a folder.
2. Open index.html in Chrome, Edge, Safari or Firefox.
3. Use the workspace dropdown to switch portals.
4. Use the left navigation to switch screens.
5. Try Add/Create, View, Edit, search/filter, CSV export, product cart/wishlist and demo checkout.

PORTALS / SCREENS
- Platform Admin: overview, organizations, vendors, catalog approval, all orders, finance & settlements, plugin registry, audit & security
- Organization Admin: overview, members & roles, stores, settings, reports, activity log
- Vendor Portal: overview, products, inventory, orders, fulfilment & shipping, returns, finance, business settings
- Vendor Plugin Portal: overview, discover plugins, installed plugins, plugin configuration, plugin logs
- Customer Marketplace: shop, wishlist, cart & checkout, my orders, returns & refunds, addresses, help & support

HOW THE DEMO WORKS
- This is a self-contained HTML/CSS/JavaScript prototype. It does not require npm, a web server, or internet access.
- Buttons and forms simulate actions in browser memory. Data resets when the page is refreshed.
- CSV export downloads demo table data.
- Checkout is simulated. No payment is collected.
- It is NOT connected to the FastAPI Core, Next.js application, PostgreSQL/Alembic, Keycloak, Temporal, carrier APIs, or a real payment gateway.
- Before production, implement real API calls, server-side authorization and tenant isolation, validation, audit trails, error/loading states, and secure payment integration.

INDIVIDUAL SCREEN SHORTCUTS
The named HTML files are launch shortcuts that open the relevant route in index.html. Keep them in the same folder as index.html.
