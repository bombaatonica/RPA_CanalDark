import os
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv

# Carrega as variáveis de ambiente
load_dotenv()

# Carrega o caminho do profile do Chrome via variável de ambiente ou usa um padrão
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", r"C:\Temp\ChromeProfileFirefly")

def ensure_logged_in(page):
    print("[RPA Firefly] Verificando status de login na Adobe...")
    did_login = False
    try:
        # Passo 1: Clicar no botão do perfil (cabeçalho)
        profile_btn = page.locator("button[data-test-id='unav-profile--sign-in'], button.profile-comp").first
        
        try:
            profile_btn.wait_for(state="visible", timeout=10000)
            print("[RPA Firefly] Botão de perfil (Fazer logon) encontrado! Clicando...")
            profile_btn.click()
            page.wait_for_timeout(2000)
            
            # Passo 2: Insistir na procura do sp-link DENTRO DO IFRAME
            print("[RPA Firefly] Procurando o link 'Fazer logon' dentro do iframe (sp-link#sign-in)...")
            auth_iframe = page.frame_locator("susi-sentry iframe, iframe[src*='identity.adobe.com'], iframe#iframe").first
            
            menu_login_link = auth_iframe.locator("sp-link#sign-in").first
            menu_login_link.wait_for(state="attached", timeout=60000)
            page.wait_for_timeout(1000)
            print("[RPA Firefly] Link 'Fazer logon' encontrado no iframe! Clicando e aguardando popup...")
            
            try:
                with page.expect_popup(timeout=10000) as popup_info:
                    menu_login_link.click(force=True)
                login_context = popup_info.value
                print("[RPA Firefly] Janela de Login (Popup) detectada com sucesso!")
            except PlaywrightTimeoutError:
                print("[RPA Firefly] Nenhum popup detectado. Assumindo redirecionamento na página principal...")
                login_context = page
            
        except PlaywrightTimeoutError:
            print("[RPA Firefly] Botão de perfil não encontrado em 10s. Provavelmente já logado.")
            return False
            
        # Procura o input de email na janela correta (popup ou pagina principal)
        print("[RPA Firefly] Procurando campo de email...")
        email_input = login_context.locator("input#EmailPage-EmailField").first
        email_input.wait_for(state="visible", timeout=20000)
        
        adobe_email = os.getenv("ADOBE_EMAIL")
        if not adobe_email:
            print("[RPA Firefly] Erro: ADOBE_EMAIL não está configurado no arquivo .env!")
            return False
            
        print(f"[RPA Firefly] Tela de login detectada. Inserindo email...")
        email_input.fill(adobe_email)
        did_login = True
        
        # Botão Continuar
        continue_btn = login_context.locator("button[data-id='EmailPage-ContinueButton']").first
        if continue_btn.is_visible():
            continue_btn.click()
            
        # Espera o campo de senha
        password_input = login_context.locator("input[type='password'], input#PasswordPage-PasswordField").first
        password_input.wait_for(state="visible", timeout=25000)
        adobe_password = os.getenv("ADOBE_PASSWORD")
        if not adobe_password:
            print("[RPA Firefly] Erro: ADOBE_PASSWORD não está configurado no arquivo .env!")
            return False
            
        print("[RPA Firefly] Inserindo senha...")
        password_input.fill(adobe_password)
        
        # Botão Continuar (login)
        pass_continue_btn = login_context.locator("button[data-id='PasswordPage-ContinueButton'], button[type='submit']").first
        if pass_continue_btn.is_visible():
            pass_continue_btn.click()
            
        # Aguarda a tela inicial carregar após o login
        print("[RPA Firefly] Aguardando o processamento do login...")
        page.wait_for_timeout(8000)
        print("[RPA Firefly] Login automático concluído!")
        
    except Exception as e:
        print(f"[RPA Firefly] Exceção na verificação de Login: {e}")
        
    return did_login

def generate_image(prompt, output_path):
    """
    Usa o Playwright para gerar uma imagem no Adobe Firefly (Text-to-Image)
    e baixa a imagem gerada para o output_path.
    """
    print(f"[RPA Firefly] Gerando Imagem para o prompt: '{prompt}'")
    
    with sync_playwright() as p:
        # Iniciamos o Chrome com profile persistente para manter a sessão (login Adobe)
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_DIR,
            headless=False, # Mantenha False durante o desenvolvimento para debugar os cliques
            channel="chrome", # Usa o Chrome local instalado
            args=["--disable-extensions", "--disable-background-networking"] # Evita processos fantasmas de extensões rodando no fundo
        )
        
        page = browser.new_page()
        
        try:
            # Acesse a URL específica do gerador de imagem
            url_imagem = "https://firefly.adobe.com/generate/image?sdid=SPVLLX6H&mv=search&mv2=paidsearch"
            page.goto(url_imagem)
            
            # Garantir login automático
            if ensure_logged_in(page):
                print("[RPA Firefly] Retornando para a URL da imagem após o login...")
                page.goto(url_imagem)
                page.wait_for_timeout(3000)
            
            # Aguarde a página carregar (este seletor precisará de ajustes constantes)
            # Dica: Use `playwright codegen https://firefly.adobe.com/generate/images`
            print("[RPA Firefly] Aguardando o campo de prompt...")
            
            # Locator para o campo de texto. Firefly geralmente usa <textarea> ou <sp-textfield>
            # Usando click + insert_text para contornar erro de <sp-textfield> (Web Component) não ser um input nativo
            prompt_input = page.locator("firefly-textfield#prompt-input, textarea[aria-label='Prompt'], sp-textfield#prompt-input").first
            prompt_input.wait_for(state="visible", timeout=30000)
            prompt_input.click()
            page.keyboard.insert_text(prompt)
            
            print("[RPA Firefly] Selecionando o modelo GPT Image 2...")
            try:
                # O botão principal do picker de modelo
                model_picker = page.locator("sp-picker#model, sp-picker[data-testid='firefly-picker-model']").first
                model_picker.wait_for(state="visible", timeout=30000)
                
                # Clica para abrir
                model_picker.click()
                page.wait_for_timeout(1000)
                
                # Seleciona o GPT Image 2 na lista de opções (Shadow DOM/Menu) usando evaluate para driblar camadas sobrepostas
                gpt_model_option = page.locator("sp-menu-item[value='openai:firefly:colligo:gpt-image-2']").first
                gpt_model_option.wait_for(state="attached", timeout=10000)
                gpt_model_option.evaluate("el => el.click()")
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"[RPA Firefly] Erro ao selecionar o modelo GPT Image 2: {e}")
            
            # Clicar no botão de gerar (Gerar em PT, Generate em EN)
            generate_btn = page.locator("button:has-text('Gerar'), button:has-text('Generate'), sp-button:has-text('Gerar')").first
            # Pega o link da imagem anterior para não baixar a mesma de novo
            old_src = page.evaluate('''() => {
                const img = document.querySelector("img[data-testid='firefly-thumbnail-image'], img[src^='blob:']");
                return img ? img.src : "";
            }''')
            
            generate_btn.click()
            
            print("[RPA Firefly] Aguardando a geração da nova imagem (pode demorar)...")
            
            # Espera até que o Firefly coloque uma nova imagem na tela
            if old_src:
                page.wait_for_function(f'''() => {{
                    const imgs = Array.from(document.querySelectorAll("img[data-testid='firefly-thumbnail-image'], img[src^='blob:']"));
                    return imgs.some(img => img.src && img.src.startsWith('blob:') && img.src !== "{old_src}");
                }}''', timeout=180000)
            else:
                page.wait_for_selector("img[data-testid='firefly-thumbnail-image'], img[src^='blob:']", timeout=180000)
            
            # Garante que o container já apareceu
            # Usa .last pois as novas gerações são adicionadas no final da página/chat
            grid = page.locator("div[data-testid='collapsible-batch-grid-content'], firefly-image-generation-image-variation").last
            grid.wait_for(state="visible", timeout=30000)
            
            # Aguarda um tempinho para a renderização estabilizar
            page.wait_for_timeout(2000)
            
            print("[RPA Firefly] Baixando a imagem...")
            
            # Localiza o primeiro container da imagem gerada DENTRO deste último batch e faz o hover para exibir os botões
            variation = grid.locator("firefly-image-generation-image-variation").first
            variation.hover()
            page.wait_for_timeout(1000)
                
            # O botão de Baixar específico deste batch que aparece no hover
            download_btn = variation.locator("sp-action-button[data-testid='thumbnail-button-download']").first
            download_btn.wait_for(state="visible", timeout=15000)
            
            with page.expect_download(timeout=180000) as download_info:
                # Agora que o botão está visível pelo hover, o click normal disparará os eventos ponteiro corretos do Web Component
                download_btn.click()
                
            download = download_info.value
            download.save_as(output_path)
            
            print(f"[RPA Firefly] Imagem salva em: {output_path}")
            
            # Remove metadados (Content Credentials / C2PA) da imagem para que a Adobe
            # permita usá-la no gerador de "Image to Video".
            try:
                from PIL import Image
                img = Image.open(output_path)
                
                # Criar um novo arquivo em branco e "colar" os pixels nele apaga totalmente 
                # qualquer metadado oculto da Adobe na imagem original.
                clean_img = Image.new(img.mode, img.size)
                clean_img.paste(img)
                clean_img.save(output_path)
                print("[RPA Firefly] Credenciais de Conteúdo limpas com sucesso!")
            except Exception as e:
                print(f"[RPA Firefly] Aviso: Falha ao limpar metadados da imagem: {e}")
                
        except PlaywrightTimeoutError:
            print("[RPA Firefly] Erro de timeout: A página demorou muito a responder.")
            raise
        finally:
            browser.close()
            
    return output_path

def generate_video(image_path, prompt, output_path, skip_generation=False):
    """
    Usa o Playwright para gerar um vídeo no Adobe Firefly (Image-to-Video)
    a partir da imagem base. Se skip_generation for True, apenas baixa o vídeo existente na tela.
    """
    print(f"[RPA Firefly] Gerando Vídeo a partir da imagem: {image_path}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_DIR,
            headless=False,
            channel="chrome",
            args=["--disable-extensions", "--disable-background-networking"]
        )
        
        page = browser.new_page()
        
        try:
            url_video = "https://firefly.adobe.com/generate/video?sdid=SPVLLX6H&mv=search&mv2=paidsearch"
            page.goto(url_video)
            
            # Garantir login automático
            if ensure_logged_in(page):
                print("[RPA Firefly] Retornando para a URL do vídeo após o login...")
                page.goto(url_video)
                page.wait_for_timeout(3000)
            
            if not skip_generation:
                print("[RPA Firefly] Aguardando área de upload de vídeo...")
                
                # O upload no firefly normalmente se dá via um input hidden do tipo file
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=30000)
                upload_input.set_input_files(image_path)
                
                # Aguarda o upload processar
                page.wait_for_timeout(3000)
                
                if prompt:
                    # Locator do prompt de animação/movimento
                    # Usamos click() + insert_text() porque sp-textfield é um Web Component e .fill() pode falhar
                    video_prompt = page.locator("firefly-textfield#prompt-input, textarea[aria-label='Prompt'], sp-textfield#prompt-input").first
                    video_prompt.click()
                    page.keyboard.insert_text(prompt)
                    
                print("[RPA Firefly] Selecionando o modelo Runway Gen-4.5...")
                try:
                    # O botão principal do picker de modelo (aguarda ele aparecer após o upload)
                    model_picker = page.locator("sp-picker#model, sp-picker[data-testid='firefly-picker-model']").first
                    model_picker.wait_for(state="visible", timeout=30000)
                    
                    # Abre o dropdown
                    model_picker.click()
                    page.wait_for_timeout(1500)
                    
                    # Seleciona o Runway Gen-4.5 na lista de opções usando evaluate para garantir o clique
                    runway_model_option = page.locator("sp-menu-item[value='ugs:video:runway@gen4.5']").first
                    runway_model_option.wait_for(state="attached", timeout=10000)
                    runway_model_option.evaluate("el => el.click()")
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"[RPA Firefly] Erro ao selecionar o modelo Runway Gen-4.5: {e}")
                    
                generate_btn = page.locator("button:has-text('Gerar'), button:has-text('Generate'), sp-button:has-text('Gerar')").first
                generate_btn.click()
                
                print("[RPA Firefly] Aguardando a geração do vídeo (pode demorar bastante, até 4 minutos)...")
            else:
                print("[RPA Firefly] Modo Economia (skip_generation=True): Pulando geração e baixando o último vídeo carregado na página...")
            
            import time
            start_time = time.time()
            download_btn = page.locator("firefly-media-timeline-download-button, sp-action-button[data-testid='firefly-media-timeline-download-button']").first
            
            # Loop de polling (espera até 4 minutos = 240 segundos)
            while time.time() - start_time < 240:
                # O botão de download só aparece se passarmos o mouse por cima do player de vídeo!
                player = page.locator("firefly-video-generation-core-video-player, firefly-media-timeline").first
                if player.is_visible():
                    player.hover()
                    
                # Se após o hover o botão ficar visível, quebramos o loop
                if download_btn.is_visible():
                    break
                    
                page.wait_for_timeout(2000)
            
            # Última checagem para garantir que não saiu por timeout
            download_btn.wait_for(state="visible", timeout=5000)
            page.wait_for_timeout(1000)
            
            print("[RPA Firefly] Geração concluída! Baixando o vídeo...")
            with page.expect_download(timeout=120000) as download_info:
                # O botão real fica DENTRO do shadow dom do <firefly-media-timeline-download-button>
                # O Playwright faz isso nativamente com o clique simulado, o evaluate javascript as vezes falha nisso.
                download_btn.click(force=True)
                
            download = download_info.value
            download.save_as(output_path)
            
            print(f"[RPA Firefly] Vídeo salvo em: {output_path}")
            
        except PlaywrightTimeoutError:
            print("[RPA Firefly] Erro de timeout na geração de vídeo.")
            raise
        finally:
            browser.close()
            
    return output_path

if __name__ == "__main__":
    # Teste isolado do RPA
    print("Iniciando teste de automação web. Certifique-se de que o Chrome está fechado.")
    img_out = "workspace/imagens_raw/test_image.jpg"
    generate_image("A dark fantasy tavern", img_out)
    generate_video(img_out, "Heavy rain and candle light", "workspace/videos_raw/test_video.mp4")
