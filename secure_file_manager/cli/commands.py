from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.panel import Panel
from rich.progress import track

from secure_file_manager.models import User, File
from secure_file_manager.services import FileService, ArchiveService, AuthService, JsonXmlService

class FileCommands:

    def __init__(self, file_service: FileService, console: Console):
        self.file_service = file_service
        self.console = console

    async def list_files(self, session: AsyncSession, user: User) -> None:

        try:
            files = await self.file_service.list_user_files(session, user)

            if not files:
                self.console.print("[yellow]No files found[/yellow]")
                return

            table = Table(title=f"Files for {user.username}")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Filename", style="white")
            table.add_column("Size", style="green", justify="right")
            table.add_column("Type", style="blue")
            table.add_column("Created", style="dim")
            table.add_column("Encrypted", style="red")

            for file in files:
                size_str = self._format_file_size(file.size)
                mime_type = file.mime_type or "unknown"
                encrypted_str = "Yes" if file.is_encrypted else "No"

                table.add_row(
                    str(file.id),
                    file.original_name,
                    size_str,
                    mime_type,
                    file.created_at.strftime("%Y-%m-%d %H:%M"),
                    encrypted_str
                )

            self.console.print(table)

            storage_info = self.file_service.get_storage_info(user)
            info_text = f"Files: {storage_info['file_count']} | " \
                       f"Total size: {self._format_file_size(storage_info['total_size'])}"
            self.console.print(f"[dim]{info_text}[/dim]")

        except Exception as e:
            self.console.print(f"[red]Error listing files: {e}[/red]")

    async def create_file(self, session: AsyncSession, user: User) -> None:

        try:
            filename = Prompt.ask("Enter filename")

            input_method = Prompt.ask(
                "Content input method",
                choices=["text", "file"],
                default="text"
            )

            if input_method == "text":
                content = Prompt.ask("Enter file content")
                content_bytes = content.encode('utf-8')
            else:
                source_path = Prompt.ask("Enter path to source file")
                try:
                    with open(source_path, 'rb') as f:
                        content_bytes = f.read()
                except Exception as e:
                    self.console.print(f"[red]Error reading source file: {e}[/red]")
                    return

            encrypt = Confirm.ask("Encrypt file?", default=False)

            with self.console.status("[bold green]Creating file...[/bold green]"):
                file_obj = await self.file_service.create_file(
                    session=session,
                    user=user,
                    filename=filename,
                    content=content_bytes,
                    encrypt=encrypt,
                    ip_address="CLI"
                )

            self.console.print(
                f"[green]File created successfully:[/green] {file_obj.original_name} "
                f"(ID: {file_obj.id})"
            )

        except Exception as e:
            self.console.print(f"[red]Error creating file: {e}[/red]")

    async def read_file(self, session: AsyncSession, user: User, file_id: int) -> None:

        try:
            file_obj, content = await self.file_service.read_file(
                session, user, file_id, "CLI"
            )

            try:
                text_content = content.decode('utf-8')

                panel = Panel(
                    text_content,
                    title=f"File: {file_obj.original_name}",
                    subtitle=f"Size: {self._format_file_size(len(content))}"
                )
                self.console.print(panel)

            except UnicodeDecodeError:

                self.console.print(
                    f"[yellow]Binary file ({self._format_file_size(len(content))}). "
                    f"Cannot display content.[/yellow]"
                )

                if Confirm.ask("Save to local file?"):
                    output_path = Prompt.ask("Enter output filename", default=file_obj.original_name)
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    self.console.print(f"[green]File saved to: {output_path}[/green]")

        except Exception as e:
            self.console.print(f"[red]Error reading file: {e}[/red]")

    async def update_file(self, session: AsyncSession, user: User, file_id: int) -> None:

        try:

            file_obj, current_content = await self.file_service.read_file(
                session, user, file_id, "CLI"
            )

            self.console.print(f"Updating file: {file_obj.original_name}")

            input_method = Prompt.ask(
                "Content input method",
                choices=["text", "file"],
                default="text"
            )

            if input_method == "text":

                try:
                    current_text = current_content.decode('utf-8')
                    self.console.print(f"[dim]Current content: {current_text[:100]}...[/dim]")
                except UnicodeDecodeError:
                    self.console.print("[dim]Current content: [binary data][/dim]")

                new_content = Prompt.ask("Enter new content")
                content_bytes = new_content.encode('utf-8')
            else:
                source_path = Prompt.ask("Enter path to source file")
                try:
                    with open(source_path, 'rb') as f:
                        content_bytes = f.read()
                except Exception as e:
                    self.console.print(f"[red]Error reading source file: {e}[/red]")
                    return

            with self.console.status("[bold green]Updating file...[/bold green]"):
                updated_file = await self.file_service.update_file(
                    session, user, file_id, content_bytes, "CLI"
                )

            self.console.print(f"[green]File updated successfully: {updated_file.original_name}[/green]")

        except Exception as e:
            self.console.print(f"[red]Error updating file: {e}[/red]")

    async def delete_file(self, session: AsyncSession, user: User, file_id: int) -> None:

        try:

            files = await self.file_service.list_user_files(session, user)
            file_obj = next((f for f in files if f.id == file_id), None)

            if not file_obj:
                self.console.print("[red]File not found[/red]")
                return

            if not Confirm.ask(f"Are you sure you want to delete '{file_obj.original_name}'?"):
                self.console.print("[yellow]Deletion cancelled[/yellow]")
                return

            with self.console.status("[bold red]Deleting file...[/bold red]"):
                success = await self.file_service.delete_file(
                    session, user, file_id, "CLI"
                )

            if success:
                self.console.print(f"[green]File deleted: {file_obj.original_name}[/green]")
            else:
                self.console.print("[red]Failed to delete file[/red]")

        except Exception as e:
            self.console.print(f"[red]Error deleting file: {e}[/red]")

    def _format_file_size(self, size_bytes: int) -> str:

        if size_bytes == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.1f} TB"

class ArchiveCommands:

    def __init__(self, archive_service: ArchiveService, console: Console):
        self.archive_service = archive_service
        self.console = console

    async def create_archive(self, session: AsyncSession, user: User) -> None:

        try:

            files = await self.archive_service.file_service.list_user_files(session, user)

            if not files:
                self.console.print("[yellow]No files available to archive[/yellow]")
                return

            table = Table(title="Available Files")
            table.add_column("ID", style="cyan")
            table.add_column("Filename", style="white")
            table.add_column("Size", style="green")

            for file in files:
                table.add_row(
                    str(file.id),
                    file.original_name,
                    self._format_file_size(file.size)
                )

            self.console.print(table)

            file_ids_input = Prompt.ask(
                "Enter file IDs to archive (comma-separated)",
                default="all"
            )

            if file_ids_input.lower() == "all":
                file_ids = [f.id for f in files]
            else:
                try:
                    file_ids = [int(x.strip()) for x in file_ids_input.split(',')]
                except ValueError:
                    self.console.print("[red]Invalid file IDs[/red]")
                    return

            valid_ids = [f.id for f in files]
            invalid_ids = [fid for fid in file_ids if fid not in valid_ids]
            if invalid_ids:
                self.console.print(f"[red]Invalid file IDs: {invalid_ids}[/red]")
                return

            archive_name = Prompt.ask("Enter archive name", default="archive.zip")

            with self.console.status("[bold green]Creating archive...[/bold green]"):
                archive_file = await self.archive_service.create_zip_archive(
                    session, user, file_ids, archive_name, "CLI"
                )

            self.console.print(
                f"[green]Archive created successfully:[/green] {archive_file.original_name} "
                f"(ID: {archive_file.id})"
            )

        except Exception as e:
            self.console.print(f"[red]Error creating archive: {e}[/red]")

    async def create_archive_by_ids(
        self,
        session: AsyncSession,
        user: User,
        file_ids: list[int],
        archive_name: str
    ) -> None:

        try:
            with self.console.status("[bold green]Creating archive...[/bold green]"):
                archive_file = await self.archive_service.create_zip_archive(
                    session, user, file_ids, archive_name, "CLI"
                )

            self.console.print(
                f"[green]Archive created successfully:[/green] {archive_file.original_name} "
                f"(ID: {archive_file.id})"
            )

        except Exception as e:
            self.console.print(f"[red]Error creating archive: {e}[/red]")

    async def extract_archive(self, session: AsyncSession, user: User, archive_id: int) -> None:

        try:
            with self.console.status("[bold green]Extracting archive...[/bold green]"):
                extracted_files = await self.archive_service.extract_zip_archive(
                    session, user, archive_id, "CLI"
                )

            self.console.print(f"[green]Archive extracted successfully![/green]")
            self.console.print(f"Extracted {len(extracted_files)} files:")

            for file in extracted_files:
                self.console.print(f"  • {file.original_name}")

        except Exception as e:
            self.console.print(f"[red]Error extracting archive: {e}[/red]")

    async def list_archive_contents(
        self,
        session: AsyncSession,
        user: User,
        archive_id: int
    ) -> None:

        try:
            contents = await self.archive_service.list_archive_contents(
                session, user, archive_id
            )

            if not contents:
                self.console.print("[yellow]Archive is empty[/yellow]")
                return

            table = Table(title="Archive Contents")
            table.add_column("Filename", style="white")
            table.add_column("Size", style="green", justify="right")
            table.add_column("Compressed", style="blue", justify="right")
            table.add_column("Ratio", style="cyan", justify="right")

            for item in contents:
                ratio = f"{item['compression_ratio']:.1f}:1" if item['compression_ratio'] > 0 else "N/A"

                table.add_row(
                    item['filename'],
                    self._format_file_size(item['size']),
                    self._format_file_size(item['compressed_size']),
                    ratio
                )

            self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Error listing archive contents: {e}[/red]")

    def _format_file_size(self, size_bytes: int) -> str:

        if size_bytes == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.1f} TB"

class UserCommands:

    def __init__(self, auth_service: AuthService, console: Console):
        self.auth_service = auth_service
        self.console = console

    async def show_profile(self, session: AsyncSession, user: User) -> None:

        try:
            profile_info = [
                f"[bold blue]Username:[/bold blue] {user.username}",
                f"[bold blue]User ID:[/bold blue] {user.id}",
                f"[bold blue]Account Status:[/bold blue] {'Active' if user.is_active else 'Inactive'}",
                f"[bold blue]Admin Privileges:[/bold blue] {'Yes' if user.is_admin else 'No'}",
                f"[bold blue]Account Created:[/bold blue] {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            ]

            panel = Panel(
                "\n".join(profile_info),
                title="User Profile",
                border_style="blue"
            )

            self.console.print(panel)

        except Exception as e:
            self.console.print(f"[red]Error showing profile: {e}[/red]")

    async def show_operations(
        self,
        session: AsyncSession,
        user: User,
        limit: int = 20
    ) -> None:

        try:
            from ..services import OperationService
            operation_service = OperationService()

            operations = await operation_service.get_user_operations(
                session, user.id, limit
            )

            if not operations:
                self.console.print("[yellow]No operations found[/yellow]")
                return

            table = Table(title=f"Recent Operations (Last {limit})")
            table.add_column("Time", style="cyan")
            table.add_column("Operation", style="white")
            table.add_column("Status", style="green")
            table.add_column("Details", style="dim")

            for op in operations:
                status = "✓ Success" if op.success else "✗ Failed"
                status_style = "green" if op.success else "red"

                details = op.details or ""
                if len(details) > 50:
                    details = details[:47] + "..."

                table.add_row(
                    op.created_at.strftime("%m-%d %H:%M"),
                    op.operation_type.value,
                    Text(status, style=status_style),
                    details
                )

            self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Error showing operations: {e}[/red]")

class JsonXmlCommands:

    def __init__(self, file_service: FileService, json_xml_service: JsonXmlService, console: Console):
        self.file_service = file_service
        self.json_xml_service = json_xml_service
        self.console = console

    async def read_json(self, session: AsyncSession, user: User, filename: str) -> None:

        try:

            content = await self.file_service.read_file_content(session, user, filename)
            if content is None:
                self.console.print(f"[red]File '{filename}' not found[/red]")
                return

            content_str = content.decode('utf-8', errors='replace')
            json_data = self.json_xml_service.safe_load_json(content_str)

            formatted_json = self.json_xml_service.safe_dump_json(json_data, indent=2)

            panel = Panel(
                formatted_json,
                title=f"JSON File: {filename}",
                title_align="left",
                padding=(1, 2),
                expand=False
            )
            self.console.print(panel)

        except Exception as e:
            self.console.print(f"[red]Error reading JSON file: {e}[/red]")

    async def write_json(self, session: AsyncSession, user: User, filename: str, directory_id=None) -> None:

        try:
            self.console.print("[yellow]Enter JSON data (press Ctrl+D when finished):[/yellow]")

            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass

            json_input = '\n'.join(lines)

            if not json_input.strip():
                self.console.print("[red]No JSON data provided[/red]")
                return

            json_data = self.json_xml_service.safe_load_json(json_input)

            formatted_json = self.json_xml_service.safe_dump_json(json_data, indent=2)

            await self.file_service.create_file(
                session=session,
                user=user,
                filename=filename,
                content=formatted_json.encode('utf-8'),
                encrypt=False,
                directory_id=directory_id,
                ip_address="CLI"
            )

            self.console.print(f"[green]JSON file '{filename}' created successfully[/green]")

        except Exception as e:
            self.console.print(f"[red]Error creating JSON file: {e}[/red]")

    async def read_xml(self, session: AsyncSession, user: User, filename: str) -> None:

        try:

            content = await self.file_service.read_file_content(session, user, filename)
            if content is None:
                self.console.print(f"[red]File '{filename}' not found[/red]")
                return

            content_str = content.decode('utf-8', errors='replace')
            xml_data = self.json_xml_service.safe_load_xml(content_str)

            formatted_xml = self.json_xml_service.safe_dump_xml(xml_data, root_name="root")

            panel = Panel(
                formatted_xml,
                title=f"XML File: {filename}",
                title_align="left",
                padding=(1, 2),
                expand=False
            )
            self.console.print(panel)

        except Exception as e:
            self.console.print(f"[red]Error reading XML file: {e}[/red]")

    async def write_xml(self, session: AsyncSession, user: User, filename: str, directory_id=None) -> None:

        try:
            self.console.print("[yellow]Enter XML data (press Ctrl+D when finished):[/yellow]")

            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass

            xml_input = '\n'.join(lines)

            if not xml_input.strip():
                self.console.print("[red]No XML data provided[/red]")
                return

            xml_data = self.json_xml_service.safe_load_xml(xml_input)

            formatted_xml = self.json_xml_service.safe_dump_xml(xml_data)

            await self.file_service.create_file(
                session=session,
                user=user,
                filename=filename,
                content=formatted_xml.encode('utf-8'),
                encrypt=False,
                directory_id=directory_id,
                ip_address="CLI"
            )

            self.console.print(f"[green]XML file '{filename}' created successfully[/green]")

        except Exception as e:
            self.console.print(f"[red]Error creating XML file: {e}[/red]")

    async def validate_json(self, session: AsyncSession, user: User, filename: str) -> None:

        try:

            content = await self.file_service.read_file_content(session, user, filename)
            if content is None:
                self.console.print(f"[red]File '{filename}' not found[/red]")
                return

            content_str = content.decode('utf-8', errors='replace')
            json_data = self.json_xml_service.safe_load_json(content_str)

            depth = self.json_xml_service._get_json_depth(json_data)
            size = len(content)

            self.console.print(f"[green]✓ JSON file '{filename}' is valid[/green]")
            self.console.print(f"  Size: {size} bytes")
            self.console.print(f"  Nesting depth: {depth} levels")

        except Exception as e:
            self.console.print(f"[red]✗ JSON file '{filename}' is invalid: {e}[/red]")

    async def validate_xml(self, session: AsyncSession, user: User, filename: str) -> None:

        try:

            content = await self.file_service.read_file_content(session, user, filename)
            if content is None:
                self.console.print(f"[red]File '{filename}' not found[/red]")
                return

            content_str = content.decode('utf-8', errors='replace')
            xml_data = self.json_xml_service.safe_load_xml(content_str)

            size = len(content)
            self.console.print(f"[green]✓ XML file '{filename}' is valid[/green]")
            self.console.print(f"  Size: {size} bytes")

        except Exception as e:
            self.console.print(f"[red]✗ XML file '{filename}' is invalid: {e}[/red]")