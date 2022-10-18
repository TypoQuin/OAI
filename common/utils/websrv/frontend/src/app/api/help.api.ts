import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from 'src/environments/environment';
import { of, Observable } from 'rxjs';


export interface HelpRequest {
    component: string;
    module:    string;
    object:    string;
}

export interface HelpResp {   
    text: string;
}
const hlproute = 'oaisoftmodem/helpfiles/';

@Injectable({
    providedIn: 'root',
})
export class HelpApi {
    constructor(private httpClient: HttpClient) { }

    public getHelp$ = (req : HelpRequest) => this.httpClient.get<HelpResp>(environment.backend + hlproute + req.component + "_" + req.module + "_" + req.object + ".html");
}
