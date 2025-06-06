from odoo import models, fields, api
from odoo.exceptions import UserError

class AnulacionWizard(models.TransientModel):
    _name = 'l10n_bo_bill.anulacion_wizard'
    _description = 'Wizard de Anulación de Factura'

    motivo_anulacion_id = fields.Many2one('l10n_bo_bill.motivo_anulacion', string="Motivo de Anulación", required=True)

    def confirmar_anulacion(self):
        """Método que se ejecuta al confirmar la anulación"""
        # Obtener la factura a la que se está aplicando el wizard
        factura = self.env['account.move'].browse(self.env.context.get('active_id'))

        if not factura:
            raise UserError(_("No se encontró la factura a anular."))

        # Llamar a la función de anulación y pasar el código clasificador del motivo seleccionado
        factura.action_anular_factura(self.motivo_anulacion_id.codigo_clasificador)
