from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import logging
from datetime import timedelta


_logger = logging.getLogger(__name__)
class ContingenciaInicioWizard(models.TransientModel):
    _name = 'contingencia.inicio.wizard'
    _description = 'Inicio de Contingencia'

    codigo_evento = fields.Selection(
        selection='_get_eventos_significativos',
        string="Evento Significativo",
        required=True,
        help="Selecciona el evento significativo que justifica la contingencia."
    )

    descripcion = fields.Char(string="Descripción", default="CORTE DEL SERVICIO DE INTERNET")
    
    def _get_api_url(self):
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        return direccion_apis.url

    
    def _get_eventos_significativos(self):
        base_url = self.env['account.move']._get_api_url()
        url = f"{base_url}/parametro/eventos-significativos"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            eventos = response.json()
            return [
                (str(e.get("codigoClasificador")), f"{e.get('codigoClasificador')} - {e.get('descripcion')}")
                for e in eventos if e.get("codigoClasificador")
            ]
        except Exception as e:
            _logger.error(f"Error obteniendo eventos significativos: {e}")
            return []

    def confirmar_contingencia(self):
        base_url = self._get_api_url()
        url = f"{base_url}/contingencia/registrar-inicio-evento"

        payload = {
            "idPuntoVenta": 1,
            "idSucursal": 1,
            "codigoEvento": int(self.codigo_evento),
            "descripcion": self.descripcion
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("mensaje") != "Evento registrado":
                raise UserError("No se registró el evento correctamente.")

            # ✅ Marcar contingencia
            direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
            if not direccion_api:
                raise UserError("No se encontró dirección API activa.")
            direccion_api.write({
                'contingencia': True,
                'evento_id': data.get("idEvento")
            })

            # ✅ Emitir solo la factura activa
            factura_id = self.env.context.get('active_id')
            if factura_id:
                factura = self.env['account.move'].browse(factura_id)
                if factura.state == 'draft' and factura.move_type == 'out_invoice':
                    factura.envio_sfv()
                    
            self._crear_cron_fin_contingencia()


        except requests.exceptions.RequestException as e:
            raise UserError(f"Error al enviar evento de contingencia: {e}")
        
    
    def _crear_cron_fin_contingencia(self):
        """Crea un cron job para finalizar la contingencia en 2 horas"""
        cron_name = "l10n_bo_edi.finalizar_contingencia_automatica"
        modelo = "account.move"

        # Si ya existe uno pendiente, no duplicar
        existing_cron = self.env['ir.cron'].search([('name', '=', cron_name)])
        if existing_cron:
            existing_cron.unlink()

        # Programar ejecución dentro de 2 horas desde ahora
        hora_ejecucion = fields.Datetime.now() + timedelta(minutes=5)

        self.env['ir.cron'].create({
            'name': cron_name,
            'model_id': self.env['ir.model'].search([('model', '=', modelo)], limit=1).id,
            'state': 'code',
            'code': "model.finalizar_contingencia_automatica()",
            'interval_number': 2,
            'interval_type': 'hours',
            'numbercall': 1,
            'nextcall': hora_ejecucion,
            'active': True,
        })
