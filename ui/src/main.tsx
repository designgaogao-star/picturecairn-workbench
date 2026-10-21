import { effect } from '@preact/signals';
import { render } from 'preact';
import { App } from './App';
import { restoreLastRoute } from './lib/router';
import { loadLibraries, loadTasks, persistPrefs } from './state/app';
import { startEvents } from './state/events';
import './styles.css';

restoreLastRoute();
render(<App />, document.getElementById('app')!);
effect(persistPrefs);
startEvents();
void loadLibraries();
void loadTasks();
