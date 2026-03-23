# DW BMS

Custom Odoo 17 addons for Dreamwarez Business Management System. This repository combines a core BMS module with supporting modules for accounting, budgeting, branding, dashboarding, and UI cleanup.

## Repository Overview

This repository contains the following installable addons:

| Module | Purpose |
| --- | --- |
| `DW_BMS` | Main business management module for sales, invoicing, stock, packing, customer classification, invoice import, and custom reports |
| `home` | Home dashboard with KPI cards for sales, purchases, dues, stock alerts, shipments, and job work |
| `custom_branding` | Backend and login branding changes such as title and favicon |
| `disable_odoo_online` | Removes Odoo online / odoo.com related menu bindings from the backend |
| `base_accounting_kit` | Community accounting extensions and financial reports used by `DW_BMS` |
| `base_account_budget` | Budget management dependency used by `base_accounting_kit` |

## Main Features

### `DW_BMS`

- Customer and supplier extensions
  - Customer type classification
  - Supplier type tracking
  - Duplicate partner-name validation
  - GST required for business suppliers
  - HSN fields exposed on sale and purchase lines
- Product controls
  - SKU, minimum sale price, storage location, opening stock reference, and unit fields
  - Duplicate product-name validation
  - Opening stock posting into inventory
  - Product storage location master with sync to product text field
- Sales workflow changes
  - `Rate Incl Tax` on sale order lines
  - Validation against minimum allowed sale price
  - Validation to prevent ordering more than available stock
  - Auto-calculation of total product weight on sale orders
- Invoice enhancements
  - Bill-to and ship-to address sections
  - Delivery modes such as direct delivery, ship to different address, and third-party delivery
  - Fiscal position auto-selection for intra-state vs inter-state GST
  - Invoice type based numbering for different business channels
  - Custom HSN summary handling for Indian localization flows
- Invoice import
  - XLSX upload wizard with column auto-detection and manual field mapping
  - Automatic grouping by invoice number
  - Duplicate invoice skipping
  - Auto-create customer records and products when needed
  - Tax resolution for CGST, SGST, and IGST
  - Auto-create and confirm sale orders, generate invoices, and post them
  - Import log with created, skipped, and failed entries
- Invoice export
  - XLSX export for customer invoices with tax, address, and payment-related fields
- Packing workflow
  - Packing order generated from customer invoice
  - Packing lines copied from invoice lines
  - Dispatch mode and courier company masters
  - Printable packing slip report
- Reporting and documents
  - Custom quotation report
  - Custom invoice print format
  - Partner ledger filtering by customer
  - BMS report wizard and templates
- Inventory and purchase tracking
  - Low-stock alert status
  - Purchase status lifecycle: not ordered, ordered, stock received
  - Scheduled cron for low-stock purchase status updates
- Access control
  - Dedicated dispatch, packing, and sales team groups
  - Record rules and report visibility rules

### `home`

- Adds a BMS home screen dashboard
- Provides both user-level and all-data KPI panels
- Supports filtering by date range, customer, and user
- Tracks:
  - total sales
  - total purchases
  - receivable due
  - payable due
  - low-stock products
  - pending outgoing shipments
  - pending job work or manufacturing orders

### `custom_branding`

- Custom backend browser title handling
- Custom login title
- Custom favicon

### `disable_odoo_online`

- Hides odoo.com related backend bindings and menu items

## Dependencies

### Odoo modules

`DW_BMS` depends on:

- `base`
- `base_import`
- `base_accounting_kit`
- `contacts`
- `sale_management`
- `purchase`
- `account`
- `product`
- `stock`
- `mrp`
- `hr`
- `l10n_in`

### Python packages

The custom invoice flows use these Python libraries in addition to standard Odoo requirements:

- `openpyxl` for XLSX invoice import
- `xlsxwriter` for XLSX invoice export

Install them in the same Python environment as Odoo if they are not already available.

## Installation

1. Add this repository to your Odoo `addons_path`.
2. Restart the Odoo server.
3. Update the apps list from Odoo.
4. Install modules in this order:
   - `base_account_budget`
   - `base_accounting_kit`
   - `DW_BMS`
   - `home`
   - `custom_branding`
   - `disable_odoo_online`
5. Ensure Indian localization and taxes are configured properly because the custom invoice logic assumes `l10n_in` and GST tax usage.
6. Configure invoice sequences for each invoice type used by the business.

## Invoice Types

The main module supports separate invoice sequences for these business channels:

- Flipkart WB
- Vastu Craft (Delhi)
- Daily Sales
- Flipkart MH
- KV Enterprises (Haryana)
- Website Sales
- Export Sales
- KV Enterprises (Tamil Nadu)
- KV Enterprises (Karnataka)
- KV Enterprises (Maharashtra)
- KV Enterprises (West Bengal)
- KV Enterprises (Telangana)

If a matching `ir.sequence` is not configured, invoice posting will fail for that invoice type.

## Typical Workflows

### Import customer invoices from XLSX

1. Open the invoice import wizard.
2. Upload the XLSX file.
3. Read headers and review the auto-detected column mappings.
4. Correct any field mappings if needed.
5. Run the import.
6. Review the generated import log.

During import the system can create partners and products, create sale orders, confirm them, generate invoices, and post the invoices automatically.

### Create and print a packing slip

1. Open a customer invoice.
2. Use the Packing action.
3. Review the generated packing order.
4. Set dispatch mode and courier company if required.
5. Print the packing slip report.

### Add opening stock

1. Set `Opening Stock (Reference)` on storable products.
2. Run the product action to add stock for one product, or use the batch action for all pending products.
3. The module posts inventory-adjustment style stock moves and resets pending opening quantity.

## Development Notes

- Root folder is a multi-addon repository for Odoo 17.
- `DW_BMS` is the primary business module.
- The root `README.md` documents the full repository, while some dependency modules keep their own upstream `README.rst`.
- The codebase contains custom report XML, security groups, scheduled actions, and wizard-based business flows.

## Suggested Local Addons Path

Example `addons_path` entry:

```ini
addons_path = /path/to/odoo/addons,/path/to/DW_BMS
```

## License Notes

- `DW_BMS`, `custom_branding`, and `home` are custom Dreamwarez modules.
- `base_accounting_kit` and `base_account_budget` include Cybrosys code and declare `LGPL-3`.
- `disable_odoo_online` declares `AGPL-3`.

Review each module manifest before redistribution.
