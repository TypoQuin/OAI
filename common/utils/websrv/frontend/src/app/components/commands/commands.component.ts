import { Component } from '@angular/core';
import { Observable } from 'rxjs/internal/Observable';
import { map } from 'rxjs/internal/operators/map';
import { tap, mergeMap } from 'rxjs/operators';
import { CommandsApi, IArgType, ILog } from 'src/app/api/commands.api';
import { CmdCtrl } from 'src/app/controls/cmd.control';
import { VarCtrl } from 'src/app/controls/var.control';
import { DialogService } from 'src/app/services/dialog.service';
import { LoadingService } from 'src/app/services/loading.service';


@Component({
  selector: 'app-commands',
  templateUrl: './commands.component.html',
  styleUrls: ['./commands.component.css'],
})
export class CommandsComponent {

  IOptionType = IArgType;

  vars$: Observable<VarCtrl[]>
  modules$: Observable<CmdCtrl[]>
  selectedModule?: CmdCtrl
  // selectedVar?: VarCtrl

  subvars$?: Observable<VarCtrl[]>
  cmds$?: Observable<CmdCtrl[]>
  // selectedSubCmd?: CmdCtrl
  // selectedSubVar?: VarCtrl

  args$?: Observable<VarCtrl[]>
  // selectedArg?: VarCtrl

  //table columns
  DISPLAYED_COLUMNS = [
    'component',
    'level',
    'output',
    'enabled'
  ]

  logs$: Observable<ILog[]> = new Observable<ILog[]>()

  constructor(
    public commandsApi: CommandsApi,
    public loadingService: LoadingService,
    public dialogService: DialogService
  ) {
    this.vars$ = this.commandsApi.readVariables$().pipe(
      map((vars) => vars.map(ivar => new VarCtrl(ivar)))
    );

    this.modules$ = this.commandsApi.readCommands$().pipe(
      map((cmds) => cmds.map(icmd => new CmdCtrl(icmd))),
      // tap(controls => [this.selectedCmd] = controls)
    );
  }


  onModuleSelect(control: CmdCtrl) {

    this.selectedModule = control

    this.cmds$ = this.commandsApi.readCommands$(`${control.nameFC.value}`).pipe(
      map(icmds => icmds.map(icmd => new CmdCtrl(icmd)))
    )

    this.subvars$ = this.commandsApi.readVariables$(`${control.nameFC.value}`).pipe(
      map(ivars => ivars.map(ivar => new VarCtrl(ivar))),
      // tap(controls => [this.selectedSubVar] = controls)
    )
  }

  onCmdSelect(control: CmdCtrl) {

    // this.selectedSubCmd = control

    this.args$ = this.commandsApi.readVariables$(`${this.selectedModule!.nameFC.value}/${control.nameFC.value}`).pipe(
      map(ivars => ivars.map(ivar => new VarCtrl(ivar)))
    )
  }

  onVarSubmit(control: VarCtrl) {
    this.commandsApi.setVariable$(control.api()).subscribe();
  }

  onSubVarSubmit(control: VarCtrl) {
    this.commandsApi.setVariable$(control.api(), `${this.selectedModule!.nameFC.value}`)
      .pipe(
        map(resp => this.success('setVariable ' + control.nameFC.value + ' OK', resp[0]))
      ).subscribe();
  }

  onCmdSubmit(control: CmdCtrl) {
    this.logs$ = this.commandsApi.runCommand$(control.api(), `${this.selectedModule!.nameFC.value}`).pipe(
      tap(resp => this.success('runCommand ' + control.nameFC.value + ' OK', resp.display!.join("</p><p>"))),
      map(iresp => iresp.logs!)
    );
  }

  private success = (mess: string, str: string) => this.dialogService.openDialog({
    title: mess,
    body: str,
  });


}