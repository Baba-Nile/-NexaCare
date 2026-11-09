"""Payment-provider integration placeholder. NOT IMPLEMENTED and disabled: payments are recorded manually by billing staff.
Enable only after the owner chooses a provider, supplies credentials through environment variables (never in code), and a sandbox test plan has passed:
webhook signature verification, idempotent callbacks, amount reconciliation against invoices, and failure/refund handling."""
class ProviderNotConfigured(RuntimeError): pass
def charge(*_, **__):
    raise ProviderNotConfigured("No payment provider is configured.")
