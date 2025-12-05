import asyncio
import sys
import logging
from typing import Optional
import click
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from loguru import logger

logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)

from secure_file_manager.database import get_database_manager, get_db_session
from secure_file_manager.services import (
    AuthService, FileService, ArchiveService,
    CryptoService, OperationService, DirectoryService, JsonXmlService
)
from secure_file_manager.models import User, Directory
from secure_file_manager.cli.commands import FileCommands, ArchiveCommands, UserCommands, JsonXmlCommands

class SecureFileManagerCLI:

    def __init__(self):
        self.console = Console()
        self.current_user: Optional[User] = None

        self.crypto_service = CryptoService()
        self.operation_service = OperationService()
        self.auth_service = AuthService(self.crypto_service, self.operation_service)
        self.file_service = FileService(self.crypto_service, self.operation_service)
        self.archive_service = ArchiveService(self.file_service, self.operation_service)
        self.directory_service = DirectoryService()
        self.json_xml_service = JsonXmlService()

        self.file_commands = FileCommands(self.file_service, self.console)
        self.archive_commands = ArchiveCommands(self.archive_service, self.console)
        self.user_commands = UserCommands(self.auth_service, self.console)
        self.json_xml_commands = JsonXmlCommands(self.file_service, self.json_xml_service, self.console)

        self.current_path = "/"
        self.current_directory: Optional[Directory] = None

    async def initialize(self) -> None:
        try:

            logger.remove()
            logger.add(
                sys.stderr,
                level="ERROR",
                format="<level>{level}: {message}</level>"
            )

            db_manager = get_database_manager()
            await db_manager.initialize()

            self.console.print(
                Panel.fit(
                    "[bold green]Secure File Manager[/bold green]\n"
                    "[dim]Modern file management with security built-in[/dim]",
                    border_style="green"
                )
            )

        except Exception as e:
            self.console.print(f"[bold red]Failed to initialize application: {e}[/bold red]")
            sys.exit(1)

    async def login_flow(self) -> bool:
        while self.current_user is None:
            self.console.print("\n[bold blue]Authentication Required[/bold blue]")
            choice = Prompt.ask(
                "Choose an option",
                choices=["login", "register", "quit"],
                default="login"
            )

            if choice == "quit":
                return False
            elif choice == "login":
                await self._handle_login()
            elif choice == "register":
                await self._handle_register()

        return True

    async def _handle_login(self) -> None:
        username = Prompt.ask("Username")
        password = Prompt.ask("Password", password=True)

        async for session in get_db_session():
            user = await self.auth_service.authenticate_user(
                session, username, password, "CLI"
            )
            if user:
                self.current_user = user
                self.console.print(f"[green]Welcome, {user.username}![/green]")
            else:
                self.console.print("[red]Invalid credentials[/red]")

    async def _handle_register(self) -> None:
        username = Prompt.ask("Choose a username")
        password = Prompt.ask("Choose a password", password=True)
        confirm_password = Prompt.ask("Confirm password", password=True)

        if password != confirm_password:
            self.console.print("[red]Passwords do not match[/red]")
            return

        try:
            async for session in get_db_session():
                user = await self.auth_service.register_user(
                    session, username, password
                )
                self.console.print(f"[green]User {user.username} registered successfully![/green]")
        except ValueError as e:
            self.console.print(f"[red]Registration failed: {e}[/red]")

    async def main_loop(self) -> None:
        while True:
            try:
                self._display_menu()
                choice = Prompt.ask("Enter command", default="help")

                parts = choice.strip().split()
                if not parts:
                    continue

                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                if command in ["quit", "q", "exit"]:
                    if Confirm.ask("Are you sure you want to quit?"):
                        break

                await self._execute_command(command, args)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'quit' to exit[/yellow]")
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                logger.error(f"CLI error: {e}")

    async def _execute_command(self, command: str, args: list[str]) -> None:

        if not self.current_user:
            if command not in ["help", "register", "login"]:
                self.console.print("[red]Please login first[/red]")
                return

        if command == "ls":
            await self._handle_ls(args)
        elif command == "cd":
            await self._handle_cd(args)
        elif command == "pwd":
            self._handle_pwd()
        elif command == "clear":
            self.console.clear()

        elif command == "register":
            await self._handle_register()
        elif command == "login":
            await self._handle_login()

        elif command == "disk":
            await self._handle_disk()

        elif command == "touch":
            await self._handle_touch(args)
        elif command == "cat":
            await self._handle_cat(args)
        elif command == "rm":
            await self._handle_rm(args)
        elif command == "wr":
            await self._handle_wr(args)
        elif command == "nano":
            await self._handle_nano(args)
        elif command == "shared":
            await self._handle_shared(args)
        elif command == "copy":
            await self._handle_copy(args)
        elif command == "create_zipbomb":
            await self._handle_create_zipbomb(args)

        elif command == "mkdir":
            await self._handle_mkdir(args)
        elif command == "rmdir":
            await self._handle_rmdir(args)

        elif command == "mv":
            await self._handle_mv(args)

        elif command == "zip":
            await self._handle_zip(args)
        elif command == "unzip":
            await self._handle_unzip(args)

        elif command == "json_read":
            await self._handle_json_read(args)
        elif command == "json_write":
            await self._handle_json_write(args)
        elif command == "json_validate":
            await self._handle_json_validate(args)
        elif command == "xml_read":
            await self._handle_xml_read(args)
        elif command == "xml_write":
            await self._handle_xml_write(args)
        elif command == "xml_validate":
            await self._handle_xml_validate(args)

        elif command == "help":
            self._display_help()

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")
            self.console.print("[dim]Type 'help' for available commands[/dim]")

    def _display_menu(self) -> None:

        if self.current_user:
            user_info = f"[bold blue]{self.current_user.username}[/bold blue]"
            if self.current_user.is_admin:
                user_info += " [red](Admin)[/red]"

            prompt = f"\n{user_info}:{self.current_path}$ "
            self.console.print(prompt, end="")
        else:
            self.console.print("\n[dim]Not logged in - use 'login' or 'register'[/dim]")

    def _display_help(self) -> None:

        help_table = Table(title="Available Commands", show_header=True)
        help_table.add_column("Command", style="cyan", no_wrap=True)
        help_table.add_column("Description", style="white")

        commands = [

            ("ls [path]", "List files and directories"),
            ("cd <path>", "Change directory (.., /, /path)"),
            ("pwd", "Show current directory"),
            ("clear", "Clear screen"),

            ("register", "Create new account"),
            ("login", "Login to account"),

            ("disk", "Show storage information"),

            ("touch <filename>", "Create new file"),
            ("cat <filename>", "Read file content"),
            ("rm <filename>", "Delete file"),
            ("wr <filename>", "Append to file"),
            ("nano <filename>", "Edit file content"),
            ("shared", "List shared files"),
            ("copy <shared_file> [new_name]", "Copy file from shared directory"),
            ("create_zipbomb <name>", "Create test ZIP bomb (for security testing)"),

            ("mkdir <dirname>", "Create directory"),
            ("rmdir [-r] <dirname>", "Remove directory (use -r for recursive)"),

            ("mv <source> <dest>", "Move/rename files or directories"),

            ("zip <archive> <files...>", "Create ZIP archive"),
            ("unzip <archive>", "Extract ZIP archive"),

            ("json_read <filename>", "Read and display JSON file"),
            ("json_write <filename>", "Create/update JSON file"),
            ("json_validate <filename>", "Validate JSON file format"),

            ("xml_read <filename>", "Read and display XML file"),
            ("xml_write <filename>", "Create/update XML file"),
            ("xml_validate <filename>", "Validate XML file format"),

            ("help", "Show this help"),
            ("quit", "Exit application")
        ]

        for command, description in commands:
            help_table.add_row(command, description)

        self.console.print(help_table)

    async def _handle_ls(self, args: list[str]) -> None:

        if not self.current_user:
            return

        async for session in get_db_session():
            try:

                await self._ensure_current_directory(session)

                current_dir_id = None
                if self.current_directory:
                    current_dir_id = self.current_directory.id

                directories = await self.directory_service.list_directories(
                    self.current_path, self.current_user, session
                )

                files = await self.file_service.list_user_files(
                    session, self.current_user, directory_id=current_dir_id
                )

                self._display_directory_contents(directories, files)

            except Exception as e:
                self.console.print(f"[red]Error listing directory: {e}[/red]")

    def _display_directory_contents(self, directories: list, files: list) -> None:

        if not directories and not files:
            self.console.print("Directory is empty")
            return

        table = Table(title=f"Contents of {self.current_path}")
        table.add_column("Type", justify="left")
        table.add_column("Name", justify="left")
        table.add_column("Size", justify="right")
        table.add_column("Created", justify="center")

        for directory in directories:
            table.add_row(
                "[blue]DIR[/blue]",
                f"[blue]{directory.name}[/blue]",
                "-",
                directory.created_at.strftime("%Y-%m-%d %H:%M")
            )

        total_size = 0
        for file in files:
            size_str = self._format_file_size(file.size)
            total_size += file.size

            table.add_row(
                "[green]FILE[/green]",
                file.original_name,
                size_str,
                file.created_at.strftime("%Y-%m-%d %H:%M")
            )

        self.console.print(table)

        if files:
            total_size_str = self._format_file_size(total_size)
            self.console.print(f"Files: {len(files)} | Directories: {len(directories)} | Total size: {total_size_str}")

    async def _ensure_current_directory(self, session) -> None:

        if self.current_path == "/" and not self.current_directory:

            self.current_directory = await self.directory_service.get_or_create_root_directory(
                self.current_user, session
            )
        elif self.current_path != "/":

            self.current_directory = await self.directory_service.get_directory_by_path(
                self.current_path, self.current_user, session
            )

    async def _handle_cd(self, args: list[str]) -> None:

        if not self.current_user:
            return

        if not args:

            self.current_path = "/"
            self.current_directory = None
            self.console.print(f"Changed to: {self.current_path}")
            return

        target = args[0]

        async for session in get_db_session():
            try:

                if target == "/":
                    new_path = "/"
                elif target == ".":
                    new_path = self.current_path
                elif target == "..":
                    if self.current_path == "/":
                        new_path = "/"
                    else:
                        parts = self.current_path.rstrip('/').split('/')
                        new_path = '/'.join(parts[:-1]) or '/'
                else:

                    new_path = await self.directory_service.resolve_path(target, self.current_path)

                if new_path == "/":

                    directory = await self.directory_service.get_or_create_root_directory(
                        self.current_user, session
                    )
                else:
                    directory = await self.directory_service.get_directory_by_path(
                        new_path, self.current_user, session
                    )
                    if not directory:
                        self.console.print(f"[red]Directory '{target}' not found[/red]")
                        return

                self.current_path = new_path
                self.current_directory = directory
                self.console.print(f"Changed to: {self.current_path}")

            except Exception as e:
                self.console.print(f"[red]Error changing directory: {e}[/red]")

    def _handle_pwd(self) -> None:

        self.console.print(self.current_path)

    async def _handle_disk(self) -> None:

        if not self.current_user:
            return

        storage_info = self.file_service.get_storage_info(self.current_user)

        table = Table(title="Storage Information")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Storage Path", storage_info['storage_path'])
        table.add_row("Total Files", str(storage_info['file_count']))
        table.add_row("Total Size", self._format_bytes(storage_info['total_size']))
        table.add_row("Max File Size", self._format_bytes(storage_info['max_file_size']))

        self.console.print(table)

    async def _handle_touch(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: touch <filename>[/red]")
            return

        filename = args[0]

        async for session in get_db_session():
            try:

                await self._ensure_current_directory(session)

                current_dir_id = None
                if self.current_directory:
                    current_dir_id = self.current_directory.id

                file_obj = await self.file_service.create_file(
                    session=session,
                    user=self.current_user,
                    filename=filename,
                    content=b"",
                    encrypt=False,
                    directory_id=current_dir_id,
                    ip_address="CLI"
                )
                self.console.print(f"[green]Created file: {file_obj.original_name}[/green]")
            except Exception as e:
                self.console.print(f"[red]Error creating file: {e}[/red]")

    async def _handle_cat(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: cat <filename>[/red]")
            return

        filename = args[0]

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, filename
            )

            if not file_obj:
                self.console.print(f"[red]File not found: {filename}[/red]")
                return

            await self.file_commands.read_file(session, self.current_user, file_obj.id)

    async def _handle_rm(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: rm <filename>[/red]")
            return

        filename = args[0]

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, filename
            )

            if not file_obj:
                self.console.print(f"[red]File not found: {filename}[/red]")
                return

            await self.file_commands.delete_file(session, self.current_user, file_obj.id)

    async def _handle_wr(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: wr <filename>[/red]")
            return

        filename = args[0]
        content = Prompt.ask("Enter content to append")

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, filename
            )

            if not file_obj:
                self.console.print(f"[red]File not found: {filename}[/red]")
                return

            try:
                _, current_content = await self.file_service.read_file(
                    session, self.current_user, file_obj.id, "CLI"
                )

                new_content = current_content + content.encode('utf-8') + b'\n'

                await self.file_service.update_file(
                    session, self.current_user, file_obj.id, new_content, "CLI"
                )

                self.console.print(f"[green]Appended to file: {filename}[/green]")

            except Exception as e:
                self.console.print(f"[red]Error appending to file: {e}[/red]")

    async def _handle_nano(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: nano <filename>[/red]")
            return

        filename = args[0]

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, filename
            )

            if not file_obj:
                self.console.print(f"[red]File not found: {filename}[/red]")
                return

            await self.file_commands.update_file(session, self.current_user, file_obj.id)

    async def _handle_shared(self, args: list[str]) -> None:

        try:
            shared_files = self.file_service.list_shared_files()
            
            if not shared_files:
                self.console.print("[yellow]No shared files found[/yellow]")
                return

            table = Table(title="Shared Files")
            table.add_column("Name", style="cyan", no_wrap=True)
            table.add_column("Size", style="green", justify="right")
            table.add_column("Modified", style="dim")

            for file_info in shared_files:
                size_str = f"{file_info['size']:,} bytes"
                from datetime import datetime
                mod_time = datetime.fromtimestamp(file_info['modified']).strftime("%Y-%m-%d %H:%M")
                
                table.add_row(
                    file_info['name'],
                    size_str,
                    mod_time
                )

            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Error listing shared files: {e}[/red]")

    async def _handle_copy(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: copy <shared_filename> [new_filename][/red]")
            return

        shared_filename = args[0]
        new_filename = args[1] if len(args) > 1 else None

        async for session in get_db_session():
            try:
                await self._ensure_current_directory(session)
                
                current_dir_id = None
                if self.current_directory:
                    current_dir_id = self.current_directory.id

                file_obj = await self.file_service.copy_from_shared(
                    session=session,
                    user=self.current_user,
                    shared_filename=shared_filename,
                    new_filename=new_filename,
                    directory_id=current_dir_id,
                    ip_address="CLI"
                )

                final_name = new_filename or shared_filename
                self.console.print(f"[green]Copied shared file '{shared_filename}' as '{final_name}'[/green]")

            except Exception as e:
                self.console.print(f"[red]Error copying file: {e}[/red]")

    async def _handle_mkdir(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: mkdir <dirname>[/red]")
            return

        dirname = args[0]

        async for session in get_db_session():
            try:

                await self._ensure_current_directory(session)

                directory = await self.directory_service.create_directory(
                    name=dirname,
                    parent_path=self.current_path,
                    user=self.current_user,
                    db=session
                )

                self.console.print(f"[green]Created directory: {dirname}[/green]")

            except Exception as e:
                self.console.print(f"[red]Error creating directory: {e}[/red]")

    async def _handle_rmdir(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: rmdir [-r] <dirname>[/red]")
            return

        recursive = False
        dirname = None

        for arg in args:
            if arg in ["-r", "--recursive"]:
                recursive = True
            else:
                dirname = arg

        if not dirname:
            self.console.print("[red]Directory name required[/red]")
            return

        marker_filename = f".{dirname}_dir_marker"

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, marker_filename
            )

            if not file_obj:
                self.console.print(f"[red]Directory not found: {dirname}[/red]")
                return

            await self.file_service.delete_file(
                session, self.current_user, file_obj.id, "CLI"
            )

            self.console.print(f"[green]Removed directory: {dirname}[/green]")

    async def _handle_mv(self, args: list[str]) -> None:

        if len(args) < 2:
            self.console.print("[red]Usage: mv <source> <dest>[/red]")
            return

        source, dest = args[0], args[1]

        async for session in get_db_session():

            file_obj = await self.file_service.get_file_by_name(
                session, self.current_user, source
            )

            if not file_obj:
                self.console.print(f"[red]File not found: {source}[/red]")
                return

            try:
                _, content = await self.file_service.read_file(
                    session, self.current_user, file_obj.id, "CLI"
                )

                new_file = await self.file_service.create_file(
                    session=session,
                    user=self.current_user,
                    filename=dest,
                    content=content,
                    encrypt=file_obj.is_encrypted,
                    ip_address="CLI"
                )

                await self.file_service.delete_file(
                    session, self.current_user, file_obj.id, "CLI"
                )

                self.console.print(f"[green]Moved {source} to {dest}[/green]")

            except Exception as e:
                self.console.print(f"[red]Error moving file: {e}[/red]")

    async def _handle_zip(self, args: list[str]) -> None:

        if len(args) < 2:
            self.console.print("[red]Usage: zip <archive_name> <file1> [file2] ...[/red]")
            return

        archive_name = args[0]
        filenames = args[1:]

        async for session in get_db_session():

            file_ids = []
            for filename in filenames:
                file_obj = await self.file_service.get_file_by_name(
                    session, self.current_user, filename
                )
                if file_obj:
                    file_ids.append(file_obj.id)
                else:
                    self.console.print(f"[yellow]File not found, skipping: {filename}[/yellow]")

            if not file_ids:
                self.console.print("[red]No valid files to archive[/red]")
                return

            await self.archive_commands.create_archive_by_ids(
                session, self.current_user, file_ids, archive_name
            )

    async def _handle_unzip(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: unzip <archive_name>[/red]")
            return

        archive_name = args[0]

        async for session in get_db_session():

            archive_obj = await self.file_service.get_file_by_name(
                session, self.current_user, archive_name
            )

            if not archive_obj:
                self.console.print(f"[red]Archive not found: {archive_name}[/red]")
                return

            await self.archive_commands.extract_archive(
                session, self.current_user, archive_obj.id
            )

    def _format_bytes(self, size_bytes: int) -> str:

        if size_bytes == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0

        return f"{size_bytes:.1f} TB"

    def _format_file_size(self, size_bytes: int) -> str:

        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)

        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.1f} {size_names[i]}"

    async def _handle_json_read(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: json_read <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():
            await self.json_xml_commands.read_json(session, self.current_user, filename)

    async def _handle_json_write(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: json_write <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():

            await self._ensure_current_directory(session)
            current_dir_id = None
            if self.current_directory:
                current_dir_id = self.current_directory.id

            await self.json_xml_commands.write_json(session, self.current_user, filename, current_dir_id)

    async def _handle_json_validate(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: json_validate <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():
            await self.json_xml_commands.validate_json(session, self.current_user, filename)

    async def _handle_xml_read(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: xml_read <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():
            await self.json_xml_commands.read_xml(session, self.current_user, filename)

    async def _handle_xml_write(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: xml_write <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():

            await self._ensure_current_directory(session)
            current_dir_id = None
            if self.current_directory:
                current_dir_id = self.current_directory.id

            await self.json_xml_commands.write_xml(session, self.current_user, filename, current_dir_id)

    async def _handle_xml_validate(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: xml_validate <filename>[/red]")
            return

        filename = args[0]
        async for session in get_db_session():
            await self.json_xml_commands.validate_xml(session, self.current_user, filename)

    async def cleanup(self) -> None:

        try:
            db_manager = get_database_manager()
            await db_manager.close()
            self.console.print("[dim]Goodbye![/dim]")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def _handle_create_zipbomb(self, args: list[str]) -> None:

        if not args:
            self.console.print("[red]Usage: create_zipbomb <filename>[/red]")
            self.console.print("[dim]Example: create_zipbomb bomb.zip[/dim]")
            return

        filename = args[0]
        if not filename.endswith('.zip'):
            filename += '.zip'

        try:
            import zipfile
            import tempfile
            import os

            large_content = b'A' * (10 * 1024 * 1024)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                with zipfile.ZipFile(tmp_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:

                    for i in range(10):
                        zf.writestr(f'large_file_{i}.txt', large_content)

                tmp_path = tmp_file.name

            with open(tmp_path, 'rb') as f:
                zip_content = f.read()

            os.unlink(tmp_path)

            uncompressed_size = len(large_content) * 10
            compressed_size = len(zip_content)
            ratio = uncompressed_size / compressed_size if compressed_size > 0 else 0

            async for session in get_db_session():
                try:

                    await self._ensure_current_directory(session)

                    current_dir_id = None
                    if self.current_directory:
                        current_dir_id = self.current_directory.id

                    file_obj = await self.file_service.create_file(
                        session=session,
                        user=self.current_user,
                        filename=filename,
                        content=zip_content,
                        directory_id=current_dir_id
                    )

                    await session.commit()

                    compressed_str = self._format_file_size(compressed_size)
                    uncompressed_str = self._format_file_size(uncompressed_size)

                    self.console.print(f"[yellow]⚠️  ZIP bomb created: '{filename}'[/yellow]")
                    self.console.print(f"   Compressed size: {compressed_str}")
                    self.console.print(f"   Uncompressed size: {uncompressed_str}")
                    self.console.print(f"   Compression ratio: {ratio:.1f}:1")
                    self.console.print(f"   [red]This will trigger ZIP bomb protection when extracted![/red]")

                except Exception as e:
                    await session.rollback()
                    self.console.print(f"[red]Error creating ZIP bomb: {e}[/red]")

        except Exception as e:
            self.console.print(f"[red]Error creating ZIP bomb: {e}[/red]")

async def run_cli() -> None:

    cli = SecureFileManagerCLI()

    try:
        await cli.initialize()

        if await cli.login_flow():
            await cli.main_loop()

    except Exception as e:
        cli.console.print(f"[bold red]Application error: {e}[/bold red]")
        logger.error(f"Application error: {e}")

    finally:
        await cli.cleanup()

@click.command()
def main() -> None:

    asyncio.run(run_cli())