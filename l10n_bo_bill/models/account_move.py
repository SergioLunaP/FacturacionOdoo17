from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from datetime import datetime
import json
import requests
import logging
import base64
from datetime import datetime
import pytz


_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campos para almacenar la respuesta de la API
    codigo_estado = fields.Char(string="Código Estado")
    cuf = fields.Char(string="CUF")
    numero_factura = fields.Char(string="Número de Factura")
    url = fields.Char(string="URL")
    
    factura_cancelada = fields.Boolean(string="Factura Cancelada", default=False)
    
    payment_type_id = fields.Many2one('l10n_bo_bill.tipo_pago', string="Método de Pago", required=True)
    contingencia = fields.Boolean(string="Factura Cancelada", default=False)
    
    def _get_api_url(self):
        """Función para obtener la dirección de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])

        if not direccion_apis:
            raise UserError(_("No se encontró una configuración de la API activa."))

        if len(direccion_apis) > 1:
            raise UserError(_("Hay más de una dirección de API activa. Verifica la configuración."))

        return direccion_apis[0]  # Retorna el registro completo


    def action_envio_a_impuestos_y_confirmar(self):
        """Primero envía a impuestos y luego confirma la factura."""
        
        self.verificar_comunicacion()
        # Lógica de envío a impuestos (llama a action_envio_a_impuestos)
        self.action_envio_a_impuestos()

        # Luego de enviar a impuestos, confirma la factura
        self.action_post()  # Esto ejecuta el método de confirmación

    def action_envio_a_impuestos(self):
        """Función que genera el JSON, lo envía al endpoint y maneja la respuesta."""

        # Verificar si el cliente tiene un código_cliente
        if not self.partner_id.codigo_cliente:
            raise UserError(_("El cliente no tiene un código_cliente asignado."))

        # Buscar el punto de venta principal
        puntos_venta = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)])

        # Validar que haya un único punto de venta principal
        if not puntos_venta:
            raise UserError(_("No se encontró un Punto de Venta principal. Verifica la configuración."))
        
        if len(puntos_venta) > 1:
            raise UserError(_("Hay más de un Punto de Venta marcado como principal. Por favor revisa la configuración."))

        # Obtener el external_id del Punto de Venta principal y verificar contingencia
        punto_venta_principal = puntos_venta[0]
        id_punto_venta = punto_venta_principal.external_id
        activo = not punto_venta_principal.contingencia  # Activo es True si contingencia es False

        _logger.info("Eniviado impuestos activo: %s", activo)
        
        if punto_venta_principal.contingencia:
            self.contingencia = True
        _logger.info("Eniviado Contingenciao: %s", self.contingencia)

        # Obtener el external_id del cliente (res.partner)
        if not self.partner_id.external_id:
            raise UserError(_("El cliente no tiene un external_id asignado."))
        id_cliente = self.partner_id.external_id

        # Obtener el código del método de pago
        if not self.payment_type_id.codigo_clasificador:
            raise UserError(_("No se ha seleccionado un método de pago válido."))

        # Datos estáticos
        nit_invalido = True

        # Preparar el detalle del movimiento de las líneas de factura (account.move.line)
        detalle = []
        productos_no_homologados = []
        
        # Iterar sobre las líneas de productos de la factura
        for line in self.invoice_line_ids:
            # Verificar si el producto tiene unidad_medida_id y codigo_producto_id
            if not line.product_id.unidad_medida_id or not line.product_id.codigo_producto_id:
                productos_no_homologados.append(line.product_id.name)

            # Obtener el external_id del producto
            if not line.product_id.external_id:
                raise UserError(_("El producto %s no tiene un external_id asignado." % line.product_id.name))

            # Calcular el monto del descuento por unidad de producto
            monto_descuento = line.price_unit * (line.discount / 100)

            # Agregar los detalles del producto
            detalle.append({
                "idProducto": line.product_id.external_id,
                "cantidad": str(line.quantity),
                "montoDescuento": "{:.2f}".format(monto_descuento),
                "precio":line.price_unit
            })

        # Si hay productos no homologados, lanzar excepción
        if productos_no_homologados:
            raise UserError(_("Producto(s) no homologado(s): %s. Verifica la unidad de medida y el código del producto SIN." % ', '.join(productos_no_homologados)))

        # Obtener el registro de la API activa y asegurarse de que solo hay uno
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
        
        if not direccion_api:
            raise UserError(_("No se ha configurado una dirección de API activa."))
        
        # Construir la URL dependiendo del tipo de API
        if direccion_api.tipo == 'computarizada':
            url = f"{direccion_api.url}/factura/emitir-computarizada"
        else:
            url = f"{direccion_api.url}/factura/emitir"

        _logger.info("URL de la API seleccionada: %s", url)

        # Preparar el JSON, asignando el valor de "activo" según el campo contingencia
        data = {
            "usuario": self.partner_id.codigo_cliente,
            "idPuntoVenta": id_punto_venta,
            "idCliente": id_cliente,
            "nitInvalido": nit_invalido,
            "idSucursal": 1,
            "activo": activo,  # Activo es True si contingencia es False
            "codigoMetodoPago": self.payment_type_id.codigo_clasificador,
            "detalle": detalle,
            "cafc": False,
        }

        # Log para mostrar el body completo que se envía
        _logger.info("Cuerpo de la solicitud (JSON): %s", json.dumps(data, indent=4))

        headers = {
            'Content-Type': 'application/json',
        }

        # Enviar los datos al endpoint
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response.raise_for_status()  # Esto lanza un error si la respuesta no es exitosa
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))

        # Verificar el estado de la respuesta
        if response.status_code == 201:
            try:
                respuesta_json = response.json()
                self.codigo_estado = respuesta_json.get("codigoEstado")
                self.cuf = respuesta_json.get("cuf")
                self.numero_factura = respuesta_json.get("numeroFactura")
                self.url = respuesta_json.get("url")

                # Generar y adjuntar el PDF al chatter
                pdf_attachment_id = self.action_download_invoice_pdf()
                
                # Publicar mensaje en el chatter con el enlace al PDF
                if pdf_attachment_id:
                    attachment_url = f"/web/content/{pdf_attachment_id}?download=true"
                    message = _(
                        "Factura emitida correctamente.\n"
                        f"Código de Estado: {self.codigo_estado}\n"
                        f"CUF: {self.cuf}\n"
                        f"Número de Factura: {self.numero_factura}\n"
                        f"url: {self.url}\n"
                        f"<a href='{attachment_url}' target='_blank'>Descargar Factura (PDF)</a>"
                    )
                    self.message_post(body=message, attachment_ids=[pdf_attachment_id])

            except json.JSONDecodeError:
                raise UserError(_("La API devolvió una respuesta no válida. No se pudo decodificar el JSON.\nRespuesta de la API: %s" % response.text))
        else:
            raise UserError(_("Error en la emisión de la factura. Código: %s\nRespuesta: %s" % (response.status_code, response.text)))
        
        
    def action_download_invoice_pdf(self):
        """Función para descargar el PDF de la factura desde la API y adjuntarlo al chatter."""
        if not self.cuf or not self.numero_factura:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        # Obtener la URL base de la API desde el campo correcto del objeto direccion_api
        direccion_api = self._get_api_url()  # Aquí debería obtener el registro de dirección de la API
        base_url = direccion_api.url if isinstance(direccion_api, str) else str(direccion_api.url)

        # Verificar que la URL tenga un esquema (http o https)
        if not base_url.startswith("http"):
            base_url = "http://" + base_url

        # Completar la URL con la ruta de descarga del PDF
        full_base_url = f"{base_url}/pdf/download"

        # Parámetros que se envían a la API en la URL
        params = {
            'cufd': self.cuf,
            'numeroFactura': self.numero_factura
        }

        # Construir la URL completa para revisión y logging
        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la descarga del PDF: %s", full_url)

        try:
            # Realizar la solicitud GET con los parámetros en la URL
            response = requests.get(full_url)

            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Codificar el contenido binario del PDF a base64
                pdf_content = base64.b64encode(response.content)

                # Crear adjunto en Odoo y guardar el PDF
                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.numero_factura,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })

                # Retorna el ID del adjunto para uso en el chatter
                return attachment.id
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))


    def action_anular_factura(self, codigo_motivo_anulacion):
        """Función para anular una factura y pasar al estado 'cancel'."""
        if not self.cuf:
            raise UserError(_("No hay CUF disponible para esta factura."))

        # Buscar el punto de venta principal
        puntos_venta = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)])

        # Validar que haya un único punto de venta principal
        if not puntos_venta:
            raise UserError(_("No se encontró un Punto de Venta principal. Verifica la configuración."))
        
        if len(puntos_venta) > 1:
            raise UserError(_("Hay más de un Punto de Venta marcado como principal. Por favor revisa la configuración."))

        # Obtener el external_id del Punto de Venta principal
        id_punto_venta = puntos_venta.external_id

        # Obtener la URL de la API activa
        direccion_api = self._get_api_url()  # Asegúrate de que este método devuelve la URL correctamente
        url = f"{direccion_api.url}/factura/anular"

        # Cuerpo de la solicitud
        data = {
            'cuf': self.cuf,
            'anulacionMotivo': codigo_motivo_anulacion,  # Usar el código clasificador seleccionado
            'idPuntoVenta': id_punto_venta,  # Mandar el external_id del Punto de Venta principal
            'idSucursal':1
        }

        headers = {
            'Content-Type': 'application/json',
        }

        # Manejo del bloque try/except para la solicitud HTTP
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()  # Esto lanza una excepción si la respuesta no es exitosa
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))  # Elimina 'response.text' porque 'response' puede no estar asignado

        # Comprobar si la solicitud fue exitosa
        if response.status_code == 200:
            respuesta_json = response.json()
            codigo_estado = respuesta_json.get("codigoEstado")
            descripcion = respuesta_json.get("descripcion")

            # Si la anulación es exitosa, pasar al estado cancel
            self.write({'state': 'cancel'})

            # Registrar un mensaje en el chatter
            self.message_post(body=_("Factura anulada correctamente. Código de Estado: %s. Descripción: %s" % (codigo_estado, descripcion)))
        else:
            raise UserError(_("Error en la anulación de la factura. Código: %s\nRespuesta de la API: %s" % (response.status_code, response.text)))

        
    def action_invoice_preview(self):
        """Previsualizar el PDF de la factura desde la API."""
        if not self.cuf or not self.numero_factura:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        # Obtener la URL base de la API desde el campo correcto del objeto direccion_api
        direccion_api = self._get_api_url()  # Aquí debería obtener el registro de dirección de la API
        base_url = direccion_api.url if isinstance(direccion_api, str) else str(direccion_api.url)

        # Verificar que la URL tenga un esquema (http o https)
        if not base_url.startswith("http"):
            base_url = "http://" + base_url

        # Completar la URL con la ruta de descarga del PDF
        full_base_url = f"{base_url}/pdf/download"

        # Parámetros que se envían a la API en la URL
        params = {
            'cufd': self.cuf,
            'numeroFactura': self.numero_factura
        }

        # Construir la URL completa para revisión y logging
        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la previsualización del PDF: %s", full_url)

        try:
            # Realizar la solicitud GET con los parámetros en la URL
            response = requests.get(full_url)

            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Codificar el contenido binario del PDF a base64
                pdf_content = base64.b64encode(response.content)
                
                # Crear un archivo adjunto con el PDF
                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.numero_factura,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })

                # Retornar una acción para abrir el PDF en el navegador sin descargarlo
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s?download=false' % attachment.id,
                    'target': 'new',
                }
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))
        
        
    def verificar_comunicacion(self):
        """Mostrar siempre el wizard de contingencia, independientemente de la respuesta de la API."""
        # Obtener la URL de la API
        direccion_api = self._get_api_url()
        url = f"{direccion_api.url}/contingencia/verificar-comunicacion"
        
        try:
            # Hacer la solicitud al endpoint de verificación
            response = requests.get(url)
            
            # Verificar si la respuesta contiene JSON
            if response.status_code == 200:
                try:
                    respuesta_json = response.json()
                    _logger.info("Respuesta de verificación de comunicación: %s", respuesta_json)
                except json.JSONDecodeError:
                    _logger.warning("La respuesta de la API no es un JSON válido.")
                    self.action_mostrar_wizard_contingencia()

            else:
                _logger.error("Error al verificar la comunicación. Código: %s. Respuesta: %s", response.status_code, response.text)
            
        except requests.exceptions.RequestException as e:
            _logger.error("Error al conectar con la API de contingencia: %s", e)


    def action_mostrar_wizard_contingencia(self):
        """Método que abre el wizard de contingencia."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contingencia.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pregunta': "¿Desea entrar en modo de contingencia?"
            }
        }
        
    @api.constrains('invoice_date')
    def _check_invoice_date(self):
        bolivia_tz = pytz.timezone('America/La_Paz')
        for record in self:
            # Obtener la fecha actual en UTC-4 (Bolivia)
            bolivia_date_today = fields.Datetime.context_timestamp(self, fields.Datetime.now()).astimezone(bolivia_tz).date()
            
            # Comparar la fecha de la factura con la fecha actual en Bolivia
            if record.invoice_date and record.invoice_date != bolivia_date_today:
                raise ValidationError("La fecha de factura solo puede ser la fecha actual en UTC-4 (Bolivia).")
            
            
    def action_download_invoice_pdf_true(self):
        """Función para descargar el PDF de la factura desde la API."""
        if not self.cuf or not self.numero_factura:
            raise UserError(_("No hay CUF o número de factura disponible para esta factura."))

        # Obtener la URL base de la API desde el campo correcto del objeto direccion_api
        direccion_api = self._get_api_url()  # Aquí debería obtener el registro de dirección de la API
        base_url = direccion_api.url if isinstance(direccion_api, str) else str(direccion_api.url)
        
        # Verificar que la URL tenga un esquema (http o https)
        if not base_url.startswith("http"):
            base_url = "http://" + base_url

        # Completar la URL con la ruta de descarga del PDF
        full_base_url = f"{base_url}/pdf/download"

        # Parámetros que se envían a la API en la URL
        params = {
            'cufd': self.cuf,
            'numeroFactura': self.numero_factura
        }

        # Construir la URL completa para revisión y logging
        full_url = requests.Request('GET', full_base_url, params=params).prepare().url
        _logger.info("URL completa para la descarga del PDF: %s", full_url)

        try:
            # Realizar la solicitud GET con los parámetros en la URL
            response = requests.get(full_url)

            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Codificar el contenido binario del PDF a base64
                pdf_content = base64.b64encode(response.content)

                # Crear adjunto en Odoo y guardar el PDF
                attachment = self.env['ir.attachment'].create({
                    'name': 'Factura-%s.pdf' % self.numero_factura,
                    'type': 'binary',
                    'datas': pdf_content,
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })

                # Retornar la acción para abrir o descargar el PDF en Odoo
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s?download=true' % attachment.id,
                    'target': 'new',
                }
            else:
                _logger.error("Error al descargar el PDF. Código de estado: %s. Respuesta: %s", response.status_code, response.text)
                raise UserError(_("Error al descargar el PDF. Código de estado: %s" % response.status_code))
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error al conectar con la API: %s" % e))
        
    def abrir_url(self):
        """Abre la URL almacenada en el campo url del registro"""
        for record in self:
            if record.url:
                return {
                    'type': 'ir.actions.act_url',
                    'url': record.url,
                    'target': 'new',  # Esto abrirá la URL en una nueva pestaña
                }
            else:
                raise UserError("No hay una URL definida para este registro.")
            
    def finalizar_contingencia(self):
        """Método para finalizar el modo de contingencia usando el idEvento del punto de venta."""
        
        # Buscar el punto de venta principal
        punto_venta_principal = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)], limit=1)
        if not punto_venta_principal:
            raise UserError(_("No se encontró un Punto de Venta principal configurado."))

        # Obtener el idEvento del punto de venta
        id_evento = punto_venta_principal.id_evento
        if not id_evento:
            raise UserError(_("No hay un idEvento registrado para el Punto de Venta en contingencia."))

        api_url = f"{self._get_api_url2()}/contingencia/registrar-fin-evento/{id_evento}"
        
        # Registrar la URL en los logs para verificar
        _logger.info("URL completa para finalizar contingencia: %s", api_url)
        
        
        try:
            # Enviar la solicitud a la API para finalizar el evento de contingencia
            response = requests.post(api_url)
            response.raise_for_status()  # Verifica si hubo un error en la solicitud

            # Manejar la respuesta de la API
            if response.status_code == 200:
                respuesta_json = response.json()
                _logger.info("Respuesta de finalizar contingencia: %s", respuesta_json)

                # Desactivar el modo de contingencia en el punto de venta y en la factura
                punto_venta_principal.write({'contingencia': False})
                self.write({'contingencia': False})

                # Registrar un mensaje en el chatter
                mensaje = respuesta_json.get("mensaje", "Contingencia finalizada correctamente.")
                self.message_post(body=_(f"{mensaje}. idEvento: {id_evento}"))

            else:
                raise UserError(_("Error al finalizar la contingencia: %s" % response.text))

        except requests.exceptions.RequestException as e:
            _logger.error("Error al conectar con la API: %s", e)
            raise UserError(_("Error al conectar con la API: %s" % e))
        
    def _get_api_url2(self):
        """Función para obtener la dirección de la API activa"""
        direccion_api = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

        if not direccion_api:
            raise UserError(_("No se encontró una configuración de la API activa."))

        # Asegurarse de que la URL tenga esquema (http o https)
        url = direccion_api.url
        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        return url