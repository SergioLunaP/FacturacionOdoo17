from odoo import models, api, fields, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    external_id = fields.Char(string='ID externo', invisible=True)
    unidad_medida_id = fields.Many2one('l10n_bo_bill.unidades_medida', string="Unidad de Medida", help="Unidad de Medida del producto", required=True)
    codigo_producto_id = fields.Many2one('l10n_bo_bill.producto_servicio', string="Código Producto SIN", help="Código Producto según la normativa SIN", required=True)
    viene_de_api = fields.Boolean(default=False, string="Viene de la API", help="Indica si el producto fue importado desde la API")

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    @api.model
    def create(self, vals):
        """Sobrescribir el método create para crear el producto en la API simultáneamente"""
        # Crear el producto en Odoo primero
        product = super(ProductTemplate, self).create(vals)

        # Verificar si el producto no proviene de la API y no tiene external_id
        if not product.viene_de_api and not product.external_id:
            # Llamar a la función para enviar los datos a la API si no tiene un external_id
            product.enviar_datos_a_api()

        return product

    def write(self, vals):
        """Sobrescribir el método write para permitir la actualización en Odoo sin enviar a la API si viene_de_api=True"""
        # Detectar si el precio de venta ha cambiado
        if 'list_price' in vals:
            # Obtener el nuevo precio
            new_price = vals['list_price']

            # Buscar líneas de facturas en borrador que usen este producto
            draft_invoices = self.env['account.move.line'].search([
                ('product_id.product_tmpl_id', 'in', self.ids),
                ('move_id.state', '=', 'draft')
            ])

            # Buscar líneas de órdenes de venta en borrador que usen este producto
            draft_sale_orders = self.env['sale.order.line'].search([
                ('product_id.product_tmpl_id', 'in', self.ids),
                ('order_id.state', '=', 'draft')
            ])

            # Actualizar precios en facturas
            for line in draft_invoices:
                line.price_unit = new_price

            # Actualizar precios en órdenes de venta
            for line in draft_sale_orders:
                line.price_unit = new_price

        # Llamar al método original para guardar los cambios en el producto
        result = super(ProductTemplate, self).write(vals)

        # Después de actualizar el producto en Odoo, actualizar los datos en la API solo si no viene de la API
        for product in self:
            # Solo actualizar en la API si el producto no viene de la API y tiene un `external_id`
            if not product.viene_de_api and product.external_id:
                product.actualizar_datos_en_api()

        return result


    def enviar_datos_a_api(self):
        """Función para enviar los datos del producto a la API después de crear el producto en Odoo"""
        api_url = f"{self._get_api_url()}/item/crear-item"
        
        # Crear el payload con los datos del producto
        payload = {
            "codigo": self.default_code,  # O el campo que uses para el código del producto
            "descripcion": self.name,
            "unidadMedida": self.unidad_medida_id.codigo_clasificador,
            "precioUnitario": self.list_price,
            "codigoProductoSin": self.codigo_producto_id.codigo_producto,
        }

        _logger.info(f"Enviando datos a la API: {payload}")

        try:
            # Realizar la solicitud POST a la API para crear el producto
            response = requests.post(api_url, json=payload)
            if response.status_code == 201:
                _logger.info(f"Datos enviados exitosamente a la API. Respuesta: {response.json()}")
                self.external_id = response.json().get('id')
            else:
                _logger.error(f"Error al enviar datos a la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudo enviar los datos a la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al enviar los datos a la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))

    def actualizar_datos_en_api(self):
        """Función para actualizar los datos del producto en la API"""
        if not self.external_id:
            raise UserError(_("El producto no tiene un ID externo. No se puede actualizar en la API."))

        api_url = f"{self._get_api_url()}/item/actualizar-item/{self.external_id}"

        payload = {
            "codigo": self.default_code,
            "descripcion": self.name,
            "unidadMedida": self.unidad_medida_id.codigo_clasificador,
            "precioUnitario": self.list_price,
            "codigoProductoSin": self.codigo_producto_id.codigo_producto,
        }

        _logger.info(f"Enviando actualización de datos a la API: {payload}")

        try:
            response = requests.put(api_url, json=payload)
            if response.status_code == 200:
                _logger.info(f"Datos actualizados exitosamente en la API. Respuesta: {response.json()}")
            else:
                _logger.error(f"Error al actualizar los datos en la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudo actualizar los datos en la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al actualizar los datos en la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))

    def obtener_productos_desde_api(self):
        """Función para obtener los productos desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/item/obtener-items"

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
                    # Verificar si el producto ya existe en Odoo por external_id
                    if str(producto['id']) not in external_ids:
                        # Validar que el campo 'name' no esté vacío
                        if not producto.get('descripcion'):
                            _logger.warning(f"El producto con ID {producto['id']} no tiene un nombre/descripción válido. Se omitirá.")
                            continue
                        
                        _logger.info(f"Creando producto en Odoo: {producto['descripcion']}")
                        
                        # Buscar las relaciones Many2one en base al código devuelto de la API
                        unidad_medida = self.env['l10n_bo_bill.unidades_medida'].search([('codigo_clasificador', '=', producto['unidadMedida'])], limit=1)
                        codigo_producto = self.env['l10n_bo_bill.producto_servicio'].search([('codigo_producto', '=', producto['codigoProductoSin'])], limit=1)

                        # Crear el producto en Odoo
                        self.create({
                            'name': producto['descripcion'],
                            'default_code': producto.get('codigo', ''),
                            'list_price': producto.get('precioUnitario', 0.0),
                            'unidad_medida_id': unidad_medida.id if unidad_medida else False,
                            'codigo_producto_id': codigo_producto.id if codigo_producto else False,
                            'external_id': producto['id'],
                            'viene_de_api': True,  # Marcar que viene de la API
                        })
            else:
                _logger.error(f"Error al obtener productos desde la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudieron obtener los productos desde la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los productos desde la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))



