from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ProductoServicio(models.Model):
    _name = 'l10n_bo_bill.producto_servicio'
    _description = 'Producto Servicio'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo_actividad = fields.Char(string='Código Actividad', required=True)
    codigo_producto = fields.Char(string='Código Producto', required=True)
    descripcion_producto = fields.Text(string='Descripción Producto', required=True)
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, required=True)

    @api.depends('descripcion_producto')
    def _compute_name(self):
        for record in self:
            record.name = record.descripcion_producto

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError(_("No se encontró una configuración de la API activa."))
        
        if len(direccion_apis) > 1:
            raise UserError(_("Hay más de una dirección de API activa. Verifica la configuración."))

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_productos_desde_api(self):
        """Función para obtener los productos desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/productos"

        _logger.info(f"Obteniendo productos desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                productos = response.json()
                _logger.info(f"Productos obtenidos desde la API: {productos}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los productos que no están en Odoo
                for producto in productos:
                    if str(producto['id']) not in external_ids:
                        _logger.info(f"Creando producto en Odoo: {producto['descripcionProducto']}")

                        # Crear el producto/servicio en Odoo y asignar el campo 'name'
                        self.create({
                            'external_id': producto['id'],
                            'codigo_actividad': producto['codigoActividad'],
                            'codigo_producto': producto['codigoProducto'],
                            'descripcion_producto': producto['descripcionProducto'],
                            'name': producto['descripcionProducto'],  # Aseguramos que 'name' no sea nulo
                        })
            else:
                _logger.error(f"Error al obtener productos desde la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudieron obtener los productos desde la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los productos desde la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))
