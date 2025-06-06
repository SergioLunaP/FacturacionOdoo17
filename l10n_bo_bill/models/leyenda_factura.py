from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class LeyendaFactura(models.Model):
    _name = 'l10n_bo_bill.leyenda_factura'
    _description = 'Leyenda Factura'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo_actividad = fields.Char(string='Código Actividad', required=True)
    descripcion_leyenda = fields.Text(string='Descripción Leyenda', required=True)
    name = fields.Char(string="Nombre", compute='_compute_name', store=True)

    @api.depends('codigo_actividad')
    def _compute_name(self):
        """Función para asignar automáticamente el valor del campo 'name'"""
        for record in self:
            record.name = record.codigo_actividad

    def _get_api_url(self):
        """Función para obtener la URL de la API activa para leyendas"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])

        if not direccion_apis:
            raise UserError(_("No se encontró una configuración de la API activa."))

        if len(direccion_apis) > 1:
            raise UserError(_("Hay más de una dirección de API activa. Por favor, verifica la configuración."))

        return f"{direccion_apis[0].url}/leyendas"

    def obtener_leyendas_desde_api(self):
        """Función para obtener las leyendas desde la API y sincronizarlas en Odoo"""
        api_url = self._get_api_url()
        _logger.info(f"Obteniendo leyendas desde la API: {api_url}")
        # messege = 'hola'
        # return {
        #     'type': 'ir.actions.client',
        #     'tag': 'display_notification',
        #     'params': {
        #         'message': messege,
        #         'type': 'success',
        #         'sticky': False,
        #     },
        # }
        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                leyendas = response.json()
                _logger.info(f"Leyendas obtenidas desde la API: {leyendas}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear las leyendas que no están en Odoo
                for leyenda in leyendas:
                    if str(leyenda['id']) not in external_ids:
                        _logger.info(f"Creando leyenda en Odoo: {leyenda['descripcionLeyenda']}")
                        self.create({
                            'codigo_actividad': leyenda['codigoActividad'],
                            'descripcion_leyenda': leyenda['descripcionLeyenda'],
                            'external_id': leyenda['id'],
                        })
            else:
                _logger.error(f"Error al obtener leyendas desde la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudieron obtener las leyendas desde la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener las leyendas desde la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))
