from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import logging

_logger = logging.getLogger(__name__)

class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"
    _description = "Account move reversal inherit"

    
    def get_invoice_type(self):
        self.inv_type = self._context.get('inv_type')
    inv_type = fields.Boolean(compute="get_invoice_type")

    def reverse_moves(self, *args, **kwargs):
        res = super(AccountMoveReversal, self).reverse_moves(*args, **kwargs)

        active_ids = self.env.context.get('active_ids', [])
        facturas = self.env['account.move'].browse(active_ids)

        for factura in facturas:
            if not factura.l10n_bo_cuf or not factura.l10n_bo_invoice_number:
                raise UserError(f"La factura {factura.name} no tiene CUF o número de factura asignado.")

            payload = {
                "cuf": factura.l10n_bo_cuf,
                "numeroFactura": int(factura.l10n_bo_invoice_number),
                "anulacionMotivo": 1,  # Aquí podrías usar cancellation_reason_id.id si lo haces dinámico
                "idPuntoVenta": 1,
                "idSucursal": 1
            }

            api_url = factura._get_api_url()
            url = f"{api_url}/factura/anular"

            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()

                if data.get('codigoEstado') != "905":
                    raise UserError(f"No se confirmó la anulación en la API. Estado: {data.get('codigoEstado')}")

                # 🔹 Marcar la factura como anulada
                factura.write({'is_cancelled': True})

                _logger.info(f"Factura {factura.name} anulada correctamente en la API.")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Error al anular la factura {factura.name}: {e}")
                raise UserError(f"Error al anular la factura en la API: {e}")

        return res