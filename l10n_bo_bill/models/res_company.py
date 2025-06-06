import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests

_logger = logging.getLogger(__name__)

class ResCompany(models.Model):
    _inherit = 'res.company'

    external_id = fields.Integer("External ID")
    
    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        _logger.info("URL de la API activa obtenida: %s", direccion_apis[0].url)
        return direccion_apis[0].url  # Retorna la URL activa

    def synchronize_company(self):
        for company in self:
            # Determinar si se debe crear o actualizar
            if not company.external_id:
                url = f"{self._get_api_url()}/empresa"
                method = "post"  # Método HTTP para crear
            else:
                url = f"{self._get_api_url()}/empresa/{company.external_id}"
                method = "put"   # Método HTTP para actualizar

            headers = {'Content-Type': 'application/json'}
            payload = {
                'nit': company.company_registry,
                'razonSocial': company.name
            }

            _logger.info("Sincronizando empresa con payload: %s", payload)

            try:
                # Enviar la solicitud con el método adecuado (POST o PUT)
                response = getattr(requests, method)(url, json=payload, headers=headers)

                _logger.info("Respuesta de la API: Código de estado %s, Respuesta: %s", response.status_code, response.text)

                if response.status_code in [200, 201]:  # 200 para actualización exitosa, 201 para creación exitosa
                    data = response.json()
                    if method == "post":
                        company.external_id = data.get('id')  # Guardar el external_id al crear
                        _logger.info("Sincronización exitosa. External ID recibido: %s", data.get('id'))
                else:
                    error_msg = _("Error al sincronizar con la API. Código de estado: %s. Respuesta: %s") % (response.status_code, response.text)
                    _logger.error(error_msg)
                    raise UserError(error_msg)
            except requests.exceptions.RequestException as e:
                _logger.exception("No se pudo conectar a la API.")
                raise UserError(_("No se pudo conectar a la API: %s") % str(e))


    def synchronize_sucursales(self):
        """Sincronizar solo las sucursales de la empresa actual desde el endpoint"""
        url = f"{self._get_api_url()}/sucursales"
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.get(url, headers=headers)
            _logger.info("Respuesta de la API de sucursales: Código de estado %s, Respuesta: %s", response.status_code, response.text)

            if response.status_code == 200:
                sucursales_data = response.json()
                sucursales_to_create = []
                sucursales_to_update = []

                for sucursal_data in sucursales_data:
                    empresa_data = sucursal_data.get('empresa', {})
                    
                    if empresa_data.get('id') == self.external_id:
                        self.env.cr.execute("""
                            SELECT id FROM l10n_bo_bill_sucursal WHERE external_id = %s
                        """, (str(sucursal_data['id']),))
                        existing_sucursal_id = self.env.cr.fetchone()

                        if existing_sucursal_id:
                            sucursales_to_update.append((
                                sucursal_data.get('codigo'),
                                sucursal_data.get('departamento'),
                                sucursal_data.get('direccion'),
                                sucursal_data.get('municipio'),
                                sucursal_data.get('nombre'),
                                sucursal_data.get('telefono'),
                                sucursal_data.get('nombre'),  # Para el campo 'name'
                                self.id,
                                str(sucursal_data['id'])  # Convertir a cadena
                            ))
                        else:
                            sucursales_to_create.append((
                                str(sucursal_data['id']),  # Convertir a cadena
                                sucursal_data.get('codigo'),
                                sucursal_data.get('departamento'),
                                sucursal_data.get('direccion'),
                                sucursal_data.get('municipio'),
                                sucursal_data.get('nombre'),
                                sucursal_data.get('telefono'),
                                sucursal_data.get('nombre'),  # Para el campo 'name'
                                self.id
                            ))

                if sucursales_to_create:
                    self.env.cr.executemany("""
                        INSERT INTO l10n_bo_bill_sucursal (
                            external_id, codigo, departamento, direccion, municipio, nombre, telefono, name, id_empresa
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, sucursales_to_create)
                    _logger.info("Sucursales creadas: %s", [s[5] for s in sucursales_to_create])

                if sucursales_to_update:
                    self.env.cr.executemany("""
                        UPDATE l10n_bo_bill_sucursal SET
                            codigo = %s,
                            departamento = %s,
                            direccion = %s,
                            municipio = %s,
                            nombre = %s,
                            telefono = %s,
                            name = %s,
                            id_empresa = %s
                        WHERE external_id = %s
                    """, sucursales_to_update)
                    _logger.info("Sucursales actualizadas: %s", [s[4] for s in sucursales_to_update])

            else:
                error_msg = _("Error al sincronizar sucursales. Código de estado: %s. Respuesta: %s") % (response.status_code, response.text)
                _logger.error(error_msg)
                raise UserError(error_msg)

        except requests.exceptions.RequestException as e:
            _logger.exception("No se pudo conectar a la API de sucursales.")
            raise UserError(_("No se pudo conectar a la API de sucursales: %s") % str(e))
