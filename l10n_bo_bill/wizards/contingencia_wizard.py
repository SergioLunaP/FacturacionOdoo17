from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class ContingenciaWizard(models.TransientModel):
    _name = 'contingencia.wizard'
    _description = 'Wizard para confirmar entrada en modo de contingencia'
    
    pregunta = fields.Char(default="¿Desea entrar en modo de contingencia?", readonly=True)

    def action_confirmar_contingencia(self):
        """Acción al confirmar entrar en contingencia, muestra el formulario de registro del evento."""
        _logger.info("Confirmación de entrada en modo contingencia")

        # Buscar el punto de venta principal y activar contingencia
        punto_venta_principal = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)], limit=1)
        if punto_venta_principal:
            punto_venta_principal.activar_contingencia()

        # Abrir el wizard del formulario adicional para registrar el evento
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'registrar.evento.contingencia.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_cancelar(self):
        """Cerrar el wizard sin realizar ninguna acción."""
        return {'type': 'ir.actions.act_window_close'}
