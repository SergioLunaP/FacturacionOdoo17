from odoo import models, api, fields, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
import requests
import logging
import re

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    external_id = fields.Char(string='ID externo', invisible=True)
    complemento = fields.Char(string='Complemento', help="Complemento de NIT")
    codigo_cliente = fields.Char(string='Código Cliente', help="Código del cliente para la integración con la API", required=True)
    viene_de_api = fields.Boolean(string='Viene de la API', default=False, help="Indica si el contacto fue importado desde la API")

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
        """Sobrescribir el método create para crear el contacto en la API simultáneamente"""
        # Crear el contacto en Odoo primero
        partner = super(ResPartner, self).create(vals)

        # Verificar si el contacto no proviene de la API y no tiene external_id
        if not partner.viene_de_api and not partner.external_id:
            # Llamar a la función para enviar los datos a la API si no tiene un external_id
            partner.enviar_datos_a_api()
       
        return partner

    def write(self, vals):
        """Sobrescribir el método write para actualizar el contacto en la API simultáneamente"""
        result = super(ResPartner, self).write(vals)

        # Después de actualizar el contacto en Odoo, actualizar los datos en la API
        for partner in self:
            if partner.external_id:
                partner.actualizar_datos_en_api()

        vat = vals.get('vat')
        
        return result


    def unlink(self):
        """Sobrescribir el método unlink para eliminar el contacto en la API simultáneamente"""
        for partner in self:
            if partner.external_id and not partner.viene_de_api:
                partner.eliminar_de_api()
        return super(ResPartner, self).unlink()

    def enviar_datos_a_api(self):
        """Función para enviar los datos a la API después de crear el contacto en Odoo"""
        api_url = f"{self._get_api_url()}/api/clientes"
        
        payload = {
            "nombreRazonSocial": self.name,
            "codigoTipoDocumentoIdentidad": 1,
            "numeroDocumento": self.vat or "",
            "complemento": self.complemento or "",
            "codigoCliente": self.codigo_cliente or "",
            "email": self.email or "",
        }

        _logger.info(f"Enviando datos a la API: {payload}")

        try:
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
        """Función para actualizar los datos del contacto en la API"""
        if not self.external_id:
            raise UserError(_("El contacto no tiene un ID externo. No se puede actualizar en la API."))

        api_url = f"{self._get_api_url()}/api/clientes/{self.external_id}"

        payload = {
            "nombreRazonSocial": self.name,
            "codigoTipoDocumentoIdentidad": 1,
            "numeroDocumento": self.vat or "",
            "complemento": self.complemento or "",
            "codigoCliente": self.codigo_cliente or "",
            "email": self.email or "",
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

    def eliminar_de_api(self):
        """Función para eliminar el contacto de la API"""
        if not self.external_id:
            raise UserError(_("El contacto no tiene un ID externo. No se puede eliminar en la API."))

        api_url = f"{self._get_api_url()}/api/clientes/{self.external_id}"

        _logger.info(f"Eliminando contacto en la API: {self.external_id}")

        try:
            # Realizar la solicitud DELETE a la API
            response = requests.delete(api_url)

            # Manejar la respuesta
            if response.status_code == 204:
                _logger.info(f"Contacto eliminado exitosamente en la API.")
            else:
                _logger.error(f"Error al eliminar el contacto en la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudo eliminar el contacto en la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al eliminar el contacto en la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))

    def obtener_clientes_desde_api(self):
        """Función para obtener los clientes desde la API y crear o actualizar los que ya están en Odoo"""
        api_url = f"{self._get_api_url()}/api/clientes"

        _logger.info(f"Obteniendo clientes desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                clientes = response.json()
                _logger.info(f"Clientes obtenidos desde la API: {clientes}")

                for cliente in clientes:
                    # Buscar si el cliente ya existe en Odoo
                    cliente_odoo = self.search([('external_id', '=', str(cliente['id']))], limit=1)

                    # Si el cliente no existe, lo crea
                    if not cliente_odoo:
                        _logger.info(f"Creando cliente en Odoo: {cliente['nombreRazonSocial']}")
                        self.create({
                            'name': cliente['nombreRazonSocial'],
                            'vat': cliente['numeroDocumento'],
                            'complemento': cliente['complemento'],
                            'codigo_cliente': cliente['codigoCliente'],
                            'email': cliente['email'],
                            'external_id': cliente['id'],
                            'viene_de_api': True,
                        })
                    else:
                        # Si el cliente ya existe, verifica si hay cambios y actualiza los datos
                        updates = {}
                        if cliente_odoo.name != cliente['nombreRazonSocial']:
                            updates['name'] = cliente['nombreRazonSocial']
                        if cliente_odoo.vat != cliente['numeroDocumento']:
                            updates['vat'] = cliente['numeroDocumento']
                        if cliente_odoo.complemento != cliente['complemento']:
                            updates['complemento'] = cliente['complemento']
                        if cliente_odoo.codigo_cliente != cliente['codigoCliente']:
                            updates['codigo_cliente'] = cliente['codigoCliente']
                        if cliente_odoo.email != cliente['email']:
                            updates['email'] = cliente['email']

                        # Si hay actualizaciones, las aplica
                        if updates:
                            _logger.info(f"Actualizando cliente en Odoo: {cliente_odoo.name} con cambios {updates}")
                            cliente_odoo.write(updates)
            else:
                _logger.error(f"Error al obtener clientes desde la API: {response.status_code} {response.text}")
                raise UserError(_("No se pudieron obtener los clientes desde la API. Error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los clientes desde la API: {e}")
            raise UserError(_("No se pudo conectar con la API: %s") % str(e))

    @api.constrains('email')
    def _check_email_format(self):
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        for record in self:
            if record.email and not re.match(email_pattern, record.email):
                raise ValidationError("Por favor, ingrese una dirección de correo válida.")